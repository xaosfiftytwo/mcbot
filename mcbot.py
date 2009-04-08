#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'xaosfiftytwo'
__copyright__ = 'xaosfiftytwo 2009'
__license__ = 'LGPL v3'

import time
import sys
import re

import icsbot
import icsbot.status
import icsbot.misc.regex as icsreg

import getopt

import copy

__usage__ = """
To start mcbot:
in linux:
   from the directory where you installed mcbot:
          python [-O[O]] ./mcbot.py [-h|--help] [-t|--testing]
                 -O[O]       : no debugging
                 without -O  : debugging info is logged in ./mcbot.log
                 -t|--testing: use test login data from logintestdata.py
                 -h|--help   : show this help message
in windows:
   dunno, don't care
"""

def usage():
    print __usage__

# handle command line options
try:
    opts, args = getopt.getopt(sys.argv[1:], "bht", ["borg", "help", "testing"])
except getopt.GetoptError, err:
    # print help information and exit:
    print str(err) # will print something like "option -a not recognized"
    usage()
    sys.exit(2)
testing = False
borg    = False
for o, a in opts:
    if o in ("-t", "--testing"):
        testing = True
    elif o in ("-h", "--help"):
        usage()
        sys.exit()
    elif o in ("-b", "--borg"):
        borg = True
    else:
        assert False, "unhandled option"
        
if testing:
    from logintestdata import me, password, admin, finger_text
else:
    from logindata import me, password, admin, finger_text 

re_empty = re.compile("^(\s)*$")
def is_empty(text):
    """
    """
    return re_empty.match(text) and True or False
    
tells_file = file('tell.log', 'a')
def tell_logger(tell):
    tells_file.write(time.strftime('%d-%m %H:%M: ', time.localtime()) + ': ' +  tell)
    tells_file.flush()

class Log(object):
    """
    Warning: use \n at the end of a line, not at the beginning, or the last line gets
    stuck in the buffer!
    """
    def __init__(self, location):
        self.buf = ''
        self.errors = file(location, 'a')
    
    def write(self, output):
        out = str(output).split('\n')
        out[0] = self.buf + out[0]
        self.buf = out[-1]
        for spam in out[:-1]:
            self.errors.write('%s%s' % (time.strftime('\n%d-%m %H:%M: ', time.localtime()), 
                                        str(spam)))
        self.errors.flush()

    def close(self):
        self.errors.close()

errors = Log('mcbot.log')


sys.stderr = errors
# sys.stdout = errors

def printerr(msg):
    if __debug__:
        sys.stderr.write('%s\n' % msg)

if __debug__:
    import instrumentation as instr

class MCBot(icsbot.IcsBot):
    """
    """
    def __init__(self, qtell_dummy=True, unmatched_log=None, tell_logger=tell_logger):
        super(MCBot, self).__init__(qtell_dummy=True, unmatched_log=None, tell_logger=tell_logger)
        self._tsn = 0

        """
        Compound Commands:
        Non-fics commands specific for this bot.
        Usually consist of a chain of fics commands, passing the results along
        and combining them.
        """
        self._compcomms = {

            'batchrun': (self.do_batchrun,           # method to register
                         '',                         # first fics command
                         None,                       # callback when answer comes in
                         lambda usr, tags: str(usr).lower() in [me, admin]),

            'whatson' : (self.do_whatson,
                         'inchannel 177',
                         self.whatson_parse_inchannel,
                         lambda usr, tags: True)
            }

        """
        _tracker is a dict, used to keep track of ongoing batchruns.
        The keys are batchids, value is another dict with (key, value) = (tsn, True)
        (value has no importance, existence of the key means
        that corresponding transaction is ongoing). Allows to detect when
        all commands of a batch have terminated, and the log file for that
        batch can be closed.
        """
        self._tracker = dict()

        # send pre-login commands
        self.send('set style 12')
        self.send('set seek 0')
        ## self.send('set interface MonkeyClub Bot(mcbot)')
        self.send('set interface BabasChess 4.0 (build 12274)')
        self.send('+ch 85')
        self.send('+ch 101')
        self.send('+ch 177')
        # bot.send('tell 177 Remember to "set noescape 0" before you start a tl game..')
        # bot.send('tell 177 or you risk forfeit by disconnection.')

        # Warning:
        # Order of registration is important

        self.channel_loggers = {'85': Log('channel85_tells.log'),
                                '101': Log('channel101_tells.log'),
                                '177': Log('channel177_tells.log'),
                                }

        self.reg_comm('(?P<usr>[a-zA-Z]{3,17})(?:\([A-Z]+\))*\((?P<channel>[0-9]{1,3})\): (?P<message>.*)', self.respond_channel_tell)

        self.reg_comm('(?P<usr>[a-zA-Z]{3,17})(?:\([A-Z]+\))*\: (?P<message>.*)', self.respond_personal_tell)

        if __debug__:
            self.alogger = Log('anything.log')
            self.reg_comm('(?P<message>^.*$)', self.respond_to_anything)

        # register bot commands
        for key, (method, command, callback, privilege_check) in self._compcomms.iteritems():
            self.reg_tell(key, method, privilege_check)
        
        # timed commands
        t = time.time()
        self.timer(t + 60 * 5, self.timer01, t)
        # keep the connection with freechess server alive
        self.timer(t + 1, self.keep_alive, t)

        if borg:
            import mcborg
            self.myborg = mcborg.mcborg() 
        
    def get_tsn(self):
        return self._tsn

    def inc_tsn(self):
        self._tsn += 1

    def get_new_tsn(self):
        self.inc_tsn()
        return self.get_tsn()

    def set_tsn(self, tsn):
        self._tsn = tsn
    
    def is_compcomm(self, command):
        return command in self._compcomms

    def get_compcomm_definition(self, command):
        return self._compcomms[command]

    
    # methods used for batch transaction tracking
    

    def track_batch(self, batchid):
        # printerr(' > track_batch')
        # printerr('batchid=%s; _tracker=%s' % (batchid, self._tracker))
        self._tracker[batchid] = dict()
        return self._tracker[batchid]

    def track_batch_trans(self, batchid, tsn):
        # printerr(' > track_batch_trans')
        # printerr('batchid=%s; tsn=%s;_tracker=%s' % (batchid, tsn, self._tracker))
        d = self._tracker.get(batchid, None)
        if not d:
            d = self.track_batch(batchid)
        assert(d, 'track tsn: batchid not in tracker')
        d[tsn] = True

    def untrack_batch_trans(self, batchid, tsn):
        # printerr(' > untrack_batch_trans')
        # printerr('batchid=%s; tsn=%s;_tracker=%s' % (batchid, tsn, self._tracker))
        d = self._tracker.get(batchid, None)
        assert( d, 'untrack tsn: batchid not in tracker') 
        printerr('d=%s' % str(d))
        assert( tsn in d, 'untrack tsn: tsn not in tracker')
        del d[tsn]
        printerr('batchid=%s; tsn=%s;_tracker=%s' % (batchid, tsn, self._tracker))

    def untrack_batch(self, batchid):
        # printerr(' > untrack_batch')
        # printerr('batchid=%s; _tracker=%s' % (batchid, self._tracker))
        d = self._tracker.get(batchid, None)
        assert( d, 'untrack batch: batchid not in tracker') 
        assert( len(d) == 0, 'untrack batch: active transactions')
        del self._tracker[batchid]
        printerr('batchid=%s; _tracker=%s' % (batchid, self._tracker))

    def track_any_active_trans(self, batchid):
        # printerr('batchid=%s; _tracker=%s' % (batchid, self._tracker))
        # printerr(' > track_active_trans')
        d = self._tracker.get(batchid, None)
        assert( d, 'untrack batch: batchid not in tracker') 
        return len(d)

    # general usage methods

    # def execute(self, command, handler, *args, **kwargs):
    #     """Override parent execute method to make sure that any command
    #     executed in batch gets tracked.
    #     """
    #     printerr('> execute')
    #     batchid = kwargs.get('batchid', None)
    #     if batchid:
    #         self.track_batch_trans(batchid, kwargs.get('tsn', None))

    #     super().execute(self, command, handler, *args, **kwargs)

    def format_kwargs(self, kwargs):
        b = kwargs.get('blogger', None)
        if b:
            b = 'Y'
        return 'tsn=%d; user=%s; compcomm=%s; command=%s; batchid=%s; blogger=%s' % (
            kwargs.get('tsn'), 
            kwargs.get('usr'),
            kwargs.get('compcomm', None),
            kwargs.get('command'),
            kwargs.get('batchid', None),
            b)

    def do_log(self, logger, message):
        printerr('(L)-%s' % message)
        logger.write('%s\n' % message)
        
    def do_tell(self, recipient, message):
        printerr('(T)-(%s): %s' % (recipient, message))
        self.send('tell %s %s' % (recipient, message))

    def respond_to_anything(self,matches):
        # printerr(' > respond_to_anything')
        message = matches.group('message')
        # printerr('usr = %s; message = %s' % (usr, message))
        # return 'tell %s %s' % (admin, matches.group(0))
        self.alogger.write('%s\n' % message)

    def respond_channel_tell(self, matches):
        # printerr(' > respond_channel_tell')
        usr = matches.group('usr')
        channel = matches.group('channel')
        message = matches.group('message')

        usr_channel = '%s(%s)' % (usr, channel)
        if channel in self.channel_loggers.keys():
            self.channel_loggers[channel].write('%s%s\n' % (usr_channel.ljust(22), message))

        if usr == 'TeamLeague' and channel == '101' and message.startswith('Game started:'):
            # if message.find('Monkey') > -1:
            self.send('tell 177 %s' % message)

        if borg:
            if usr.lower() in ('zulugodetia', 'kirany', 'dermandarin', 'xaosfiftytwo', 'cjldx'):
                reply = self.myborg.reply(message)
                if not re_empty.match(reply):
                    self.send('tell 177 %s' % reply)
                
        # return 'tell %s %s' % (admin, matches.group(0))

    def respond_personal_tell(self, matches):
        printerr(' > respond_personal_tell')
        usr = matches.group('usr')
        message = matches.group('message')
        # printerr('usr = %s; message = %s' % (usr, message))
        # return 'tell %s %s' % (admin, matches.group(0))
        return None

    def handle_response(self, data, args, kwargs):
        """
        Handle reponse to normal FICS commands, submitted by batch
        Warning!
        responses to timed commands are handled here also, but arent logged.
        """
        printerr(' > handle_response')
        printerr('(R)<-%s' % self.format_kwargs(kwargs))
        printerr('data = %s' % (repr(data)))
        batchid = kwargs.get('batchid', None)
        blogger = kwargs.get('blogger', None)
        assert(batchid, 'no batchid?')
        # assert(blogger, 'no blogger?')
        data = data.split('\n\r')
        for line in data:
            if re_empty.match(line):
                continue
            if blogger:
                self.do_log(blogger, '%s' % line)
            else:
                printerr(line)

        self.untrack_batch_trans(batchid, kwargs.get('tsn'))

        if self.track_any_active_trans(batchid) == 0:
            self.untrack_batch(batchid)
            if blogger:
                printerr('close log file now..')
                blogger.close()
                    
        printerr('---')

    def submit_batch_commands(self, lines, usr, blogger):
        printerr(' > submit_batch_commands')

        usr = str(usr)
        timestamp = time.time()
        batchid = None
        
        for line in lines:
            tsn = self.get_new_tsn()
            if not batchid:
                batchid = tsn
            command = line
            compcomm = line.split()[0]
            if self.is_compcomm(compcomm):
                method, command, callback, privilege_check = self.get_compcomm_definition(compcomm)
                if blogger:
                    self.do_log(blogger, 'submit %s' % line)
            else:
                compcomm = None
                callback = self.handle_response
            
            if blogger:
                self.do_log(blogger, 'submit %s' % command)

            printerr('(S)->tsn=%d; batchid=%d; compcomm=%s; command=%s' %
                     (tsn, batchid, compcomm, command))

            self.track_batch_trans(batchid, tsn)

            self.execute(command, 
                         callback, 
                         [], 
                         {'usr': usr,
                          'tsn': tsn,
                          'timestamp': timestamp,
                          'batchid': batchid,
                          'blogger': blogger,
                          'compcomm': compcomm,
                          'command': command})

    def handle_batch_file(self, filename, usr, logging):
        """
        """
        # printerr("reading commands from file '%s'" % filename)
        printerr(' > handle_batch_file')
        try: 
            f = None
            f = open(filename, 'rU')
            if logging:
                blogger = Log(filename + '.log')
                self.do_log(blogger, 'submit commands from file \'%s\'' % filename) 
            else:
                blogger = None
            lines = []
            for line in f.readlines():
                line = line.rstrip()
                # munge empty lines
                if re_empty.match(line):
                    continue
                # munge comment lines
                if line.startswith('#'):
                    continue
                lines.append(line)
            
            self.submit_batch_commands(lines, usr, blogger)

        except IOError, (errno, strerror):
            printerr("Error reading file %s" % filename)
            printerr("I/O error(%s): %s" % (errno, strerror))
        # except:
        #     printerr("Unexpected error: %s" % sys.exc_info()[0])
        finally:
            if f:
                f.close()

    def do_batchrun(self, usr, args, tag):
        """
        Usage: batchrun [ -log|-nolog] file [file..]
        Executes all fics commands in 'file' in batch, and logs
        the results in file.log
        """
        printerr(' > do_batchrun')
        # printerr('usr = %s%s; command = %s %s' % 
        #          (str(usr).lower(), str(tag), 'batchrun', str(args)))
        
        arglist=str(args).split()
        logging = True
        if arglist[0] in ['-log', '-nolog']:
            if arglist[0] == '-nolog':
                logging = False
            arglist = arglist[1:]
        if len(arglist) == 0:
            printerr('** Usage: batchrun [ -log|-nolog ] file [file...]')
        else:
            for filename in arglist:
                self.handle_batch_file(filename, str(usr), logging)
                printerr("-----")

    def whatson_parse_inchannel(self, data, args, kwargs):
        printerr(' > whatson_parse_inchannel')
        printerr('(R)<-%s' % self.format_kwargs(kwargs))

        batchid = kwargs.get('batchid', None)
        blogger = kwargs.get('blogger', None)

        if batchid:
            self.untrack_batch_trans(batchid, kwargs.get('tsn'))

        data = data.split('\n\r')
        # printerr('number of lines: %d' % (len(data)))
        # for line in data:
        #     printerr(line)

        re_inchan01 = re.compile(r'^Channel (?P<channel>%s):\s(?P<handles>.*)$' % r'\d{1,3}')
        re_inchan02 = re.compile(r'(%s)' % icsreg.HANDLE)

        for line in data:
            result=re_inchan01.findall(line)
            if result:
                printerr('result = %s' % repr(result))
                channel, handles = result[0]
                result=re_inchan02.findall(handles)
                printerr('channel = %s' % (channel))
                printerr('handles = %s' % repr(result))
                usr = kwargs.get('usr')
                timestamp = time.time()
                compcomm = kwargs.get('compcomm')
                callback = self.whatson_parse_finger

                for handle in result:
                    tsn = self.get_new_tsn()
                    command = 'finger %s' % handle
            
                    printerr('(S)->tsn=%d; batchid=%s; compcomm=%s; command=%s' %
                             (tsn, batchid, compcomm, command))

                    if batchid:
                        self.track_batch_trans(batchid, tsn)

                    self.execute(command, 
                                 callback, 
                                 [],
                                 {'usr': usr,
                                  'tsn': tsn,
                                  'batchid': batchid,
                                  'timestamp': timestamp,
                                  'compcomm': compcomm,
                                  'command': command,
                                  'blogger': blogger
                                  })
            else:
                printerr(line)

        if batchid:
            if not self.track_any_active_trans(batchid):
                self.untrack_batch(batchid)
                if blogger:
                    printerr('close log file now..')
                    blogger.close()
        
    def whatson_parse_finger(self, data, args, kwargs):
        printerr(' > whatson_parse_finger')
        printerr('(R)<-%s' % self.format_kwargs(kwargs))

        batchid = kwargs.get('batchid', None)
        blogger = kwargs.get('blogger', None)

        if batchid:
            self.untrack_batch_trans(batchid, kwargs.get('tsn'))

        re1 = re.compile('\((.*)\)')
        re2 = re.compile('\s+rating')
        re3 = re.compile('^Finger of (%s)(.*):' % icsreg.HANDLE)
        message = None

        data = data.split('\n\r')
        for line in data:
            if re_empty.match(line):
                continue
            if re3.match(line):
                handle = re3.match(line).group(1)
                # print 'handle = %s' % handle
                continue
            if re1.match(line):
                message = re1.match(line).group(1)
                # print 'message = %s' % message
                break
            if re2.match(line):
                break

        if message:
            if not message.startswith('%s is ' % handle):
                message = '%s is %s' % (handle, message)

            if batchid and blogger:
                self.do_log(blogger, message)
            else:
                self.do_tell(kwargs.get('usr'), message)

        if batchid:
            if not self.track_any_active_trans(batchid):
                self.untrack_batch(batchid)
                printerr('close log file now..')
                blogger.close()
                
    def do_whatson(self, usr, args, tag):
        """
        For each handle found in channel 177 execute 'finger handle', extract
        some information and show the result in a private tell to the user that
        submitted the 'whatson' command.
        """
        printerr(' > do_whatson')
        # printerr('usr = %s%s; command = %s %s' % 
        #          (str(usr).lower(), str(tag), 'whatson', str(args)))
        compcomm = 'whatson'
        f, command, callback, privilege_check = self.get_compcomm_definition(compcomm)
        tsn = self.get_new_tsn()

        printerr('(S)->tsn=%d; compcomm=%s; command=%s' %
                 (tsn, compcomm, command))

        self.execute(command, 
                     self.whatson_parse_inchannel, 
                     [], 
                     {'usr': str(usr),
                      'tsn': tsn,
                      'timestamp': time.time(),
                      'compcom': compcomm,
                      'command': command
                      })

        printerr("-----")

    def timer01(self, run_time):
        printerr(' > timer01')
        repeat = 60 * 60 * 2
        timestamp = time.time()
        self.do_batchrun(me, '-nolog timer1', '')
        self.timer(timestamp + repeat, self.timer01, timestamp + repeat)

    def keep_alive(self, run_time):
        printerr(' > keep_alive')
        repeat = 60 * 55
        timestamp = time.time()
        self.do_batchrun(me, '-nolog keep_alive', '')
        self.timer(timestamp + repeat, self.keep_alive, timestamp + repeat)

 
# Main loop in case of disconnections, just recreating the bot right now.
# Should not actually be necessary.
while True:
    if __debug__:
        m0 = instr.memory()
        r0 = instr.resident()
        s0 = instr.stacksize()
        
        printerr('vitual memory usage  = %d' % m0)
        printerr('real memory usage    = %d' % r0)
        printerr('stack size           = %d' % s0)

    bot = MCBot(qtell_dummy=True, tell_logger=tell_logger)

    # 
    icsbot.status.Status(bot)
    usrs = bot['usrs']

    if __debug__:
        m1 = instr.memory(since=m0)
        r1 = instr.resident(since=r0)
        s1 = instr.stacksize(since=s0)
        
        printerr('vitual memory usage increment = %d' % m1)
        printerr('real memory usage increment   = %d' % r1)
        printerr('stack size increment          = %d' % s1)

    try:
        bot.connect(me, password)
    except icsbot.InvalidLogin, msg:
        print msg
        if str(msg) == 'Handle in use.':
            print 'Restarting'
            time.sleep(3)
            continue
        print 'Quitting.'
        break
    except icsbot.ConnectionClosed, msg:
        print 'Connection was lost, because:', msg
        print 'Restarting'
        time.sleep(3)
        continue
    except icsbot.socket.error, msg:
        print 'Socket error:', msg
        print 'Restarting'
        time.sleep(3)
        continue
    
    print 'Connected to FICS.'

    try:
        bot.run()
    except icsbot.ConnectionClosed, msg:
        if str(msg) == 'Someone logged in as me.':
            print 'Connection was lost, because someone logged in as me.'
            print 'Quitting.'
            break
        print 'Connection was lost, because:', msg
        print 'Restarting'
    except icsbot.socket.error, msg:
        print 'Socket error:', msg
        print 'Restarting'

    time.sleep(3)
