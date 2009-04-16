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

__usage__ = """
To start mcbot:
in linux:
   from the directory where you installed mcbot:
          python [-O[O]] ./mcbot.py [-h|--help] [-t|--testing]
                 -O[O]       : no debugging
                 without -O  : debugging info is logged in trace.log
                 -b|--borg   : include mcborg functionality
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

import logging

tell_logger = logging.getLogger('tell_logger')
tell_handler = logging.FileHandler('tell.log')
tell_handler.setLevel(logging.INFO)
tell_format = logging.Formatter('%(asctime)s %(message)s')
tell_handler.setFormatter(tell_format)
tell_logger.addHandler(tell_handler)
tell_logger.setLevel(logging.INFO)
tell_logger.__call__ = tell_logger.info

trace_logger = logging.getLogger('trace_logger')
trace_handler = logging.FileHandler('trace.log')
trace_format = logging.Formatter('%(asctime)s %(module)s %(lineno)d %(levelname)s %(message)s')
trace_handler.setFormatter(trace_format)
trace_handler.setLevel(logging.DEBUG)
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.ERROR)
trace_logger.addHandler(trace_handler)
trace_logger.addHandler(stderr_handler)
trace_logger.setLevel(logging.DEBUG)
    
class Log(object):
    """
    Warning: use \n at the end of a line, not at the beginning, or the last line gets
    stuck in the buffer!
    This class is used only for logging the results of a batchrun.
    Such runs are normally short-lived, and the logfile can be closed and disposed of
    when batchrun ends.
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

class MCBot(icsbot.IcsBot):
    """
    """
    def __init__(self, qtell_dummy=True, unmatched_log=None, tell_logger=tell_logger):
        super(MCBot, self).__init__(qtell_dummy=True, unmatched_log=None, tell_logger=tell_logger)
        self._tsn = 0

        self._compcomms = {

            'batchrun': (self.do_batchrun,           # method to register
                         '',                         # first fics command
                         None,                       # callback when answer comes in
                         lambda usr, tags: str(usr).lower() in [me, admin]),

            'whatson' : (self.do_whatson,
                         'inchannel 177',
                         self.whatson_parse_inchannel,
                         lambda usr, tags: True),

            '+borg' : (self.do_plusborg,
                       '',
                       None,
                       lambda usr, tags: str(usr).lower() in [me, admin]),

            '-borg' : (self.do_minusborg,
                       '',
                       None,
                       lambda usr, tags: str(usr).lower() in [me, admin]),

            '=borg' : (self.do_equalsborg,
                       '',
                       None,
                       lambda usr, tags: str(usr).lower() in [me, admin]),
            }
        """
        Compound Commands:
        Non-fics commands specific for this bot.
        Usually consist of a chain of fics commands, passing the results along
        and combining them.
        """

        self._tracker = {}
        """
        _tracker is a dict, used to keep track of ongoing batchruns.
        The keys are batchids, value is another dict with (key, value) = (tsn, True)
        (value has no importance, existence of the key means
        that corresponding transaction is ongoing). Allows to detect when
        all commands of a batch have terminated, and the log file for that
        batch can be closed.
        """

        # send pre-login commands
        self.send('set style 12')
        self.send('set seek 0')
        ## self.send('set interface MonkeyClub Bot(mcbot)')
        self.send('set interface BabasChess 4.0 (build 12274)')

        self.join_channels = ['85', '101', '177']
        for channel in self.join_channels:
            self.send('+ch %s' % channel)

        self.log_channels =['85', '101', '177']
        self.channel_loggers = {}
        for channel in self.log_channels:
            logger = logging.getLogger('channel_%s_logger' % channel)
            handler = logging.FileHandler('channel_%s_tell.log' % channel)
            format = logging.Formatter('%(asctime)s %(message)s')
            handler.setFormatter(format)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            self.channel_loggers[channel] = logger.info

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
        self.timer(t + 60 * 60 * 2, self.timer01, t)
        # keep the connection with freechess server alive
        self.timer(t + 1, self.keep_alive, t)

        if borg:
            import mcborg
            self.myborg = mcborg.mcborg()
            self.borg_channels = ['177']
            self.borg_handles = ['x']
        
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
        self._tracker[batchid] = dict()
        return self._tracker[batchid]

    def track_batch_trans(self, batchid, tsn):
        d = self._tracker.get(batchid, None)
        if not d:
            d = self.track_batch(batchid)
        assert(d, 'track tsn: batchid not in tracker')
        d[tsn] = True

    def untrack_batch_trans(self, batchid, tsn):
        d = self._tracker.get(batchid, None)
        assert( d, 'untrack tsn: batchid not in tracker') 
        assert( tsn in d, 'untrack tsn: tsn not in tracker')
        del d[tsn]

    def untrack_batch(self, batchid):
        d = self._tracker.get(batchid, None)
        assert( d, 'untrack batch: batchid not in tracker') 
        assert( len(d) == 0, 'untrack batch: active transactions')
        del self._tracker[batchid]
        trace_logger.debug('batchid=%s; _tracker=%s' % (batchid, self._tracker))

    def track_any_active_trans(self, batchid):
        d = self._tracker.get(batchid, None)
        assert( d, 'untrack batch: batchid not in tracker') 
        return len(d)

    # general usage methods

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
        trace_logger.debug('(L)-%s' % message)
        logger.write('%s\n' % message)
        
    def do_tell(self, recipient, message):
        trace_logger.debug('(T)-(%s): %s' % (recipient, message))
        self.send('tell %s %s' % (recipient, message))

    def respond_to_anything(self,matches):
        message = matches.group('message')
        self.alogger.write('%s\n' % message)

    def respond_channel_tell(self, matches):
        usr = matches.group('usr')
        channel = matches.group('channel')
        message = matches.group('message')

        usr_channel = '%s(%s)' % (usr, channel)
        if channel in self.channel_loggers.keys():
            self.channel_loggers[channel]('%s%s' % (usr_channel.ljust(22), message))

        if usr == 'TeamLeague' and channel == '101' and message.startswith('Game started:'):
            # if message.find('Monkey') > -1:
            self.send('tell 177 %s' % message)

        if borg and not usr == me:
            if channel in self.borg_channels:
                if 'all' in self.borg_handles or usr.lower() in self.borg_handles:
                    reply = self.myborg.reply(message)
                    retries = 3
                    while retries > 0:
                        if not re_empty.match(reply):
                            self.send('tell 177 %s' % reply)
                            break
                        else: 
                            retries -= 1

    def respond_personal_tell(self, matches):
        usr = matches.group('usr')
        message = matches.group('message')
        return None

    def handle_response(self, data, args, kwargs):
        """
        Handle reponse to normal FICS commands, submitted by batch
        Warning!
        responses to timed commands are handled here also, but arent logged.
        """
        trace_logger.debug('(R)<-%s' % self.format_kwargs(kwargs))
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
                trace_logger.debug(line)

        self.untrack_batch_trans(batchid, kwargs.get('tsn'))

        if self.track_any_active_trans(batchid) == 0:
            self.untrack_batch(batchid)
            if blogger:
                trace_logger.debug('close log file now..')
                blogger.close()
                # blogger.shutdown()
                del blogger
                    
    def submit_batch_commands(self, lines, usr, logger):
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
                if logger:
                    sef.do_log(logger, 'submit %s' % line)
            else:
                compcomm = None
                callback = self.handle_response
            
            if logger:
                self.do_log(logger, 'submit %s' % command)

            trace_logger.debug('(S)->tsn=%d; batchid=%d; compcomm=%s; command=%s' %
                     (tsn, batchid, compcomm, command))

            self.track_batch_trans(batchid, tsn)

            self.execute(command, 
                         callback, 
                         [], 
                         {'usr': usr,
                          'tsn': tsn,
                          'timestamp': timestamp,
                          'batchid': batchid,
                          'blogger': logger,
                          'compcomm': compcomm,
                          'command': command})

    def handle_batch_file(self, filename, usr, log):
        """
        """
        try: 
            f = None
            f = open(filename, 'rU')
            if log:
                # logger = logging.getLogger(filename)
                # handler = logging.FileHandler('%s.log' % filename)
                # format = logging.Formatter('%asctime)s %(message)s')
                # handler.setFormatter(format)
                # logger.addHandler(handler)
                # logger.setLevel(logging.INFO)
                logger = Log(filename + '.log')
                # logger.info('submit commands from file \'%s\'' % filename) 
            else:
                logger = None
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
            
            self.submit_batch_commands(lines, usr, logger)

        except IOError, (errno, strerror):
            trace_logger.error("Error reading batchfile.", exc_info=True)
        finally:
            if f:
                f.close()

    def do_batchrun(self, usr, args, tag):
        """
        Usage: batchrun [ -log|-nolog] file [file..]
        Executes all fics commands in 'file' in batch, and logs
        the results in file.log
        """
        arglist=str(args).split()
        logging = True
        if arglist[0] in ['-log', '-nolog']:
            if arglist[0] == '-nolog':
                logging = False
            arglist = arglist[1:]
        if len(arglist) == 0:
            trace_logger.info('** Usage: batchrun [ -log|-nolog ] file [file...]')
        else:
            for filename in arglist:
                self.handle_batch_file(filename, str(usr), logging)
                trace_logger.debug("-----")

    def whatson_parse_inchannel(self, data, args, kwargs):
        trace_logger.debug('(R)<-%s' % self.format_kwargs(kwargs))

        batchid = kwargs.get('batchid', None)
        blogger = kwargs.get('blogger', None)

        if batchid:
            self.untrack_batch_trans(batchid, kwargs.get('tsn'))

        data = data.split('\n\r')

        re_inchan01 = re.compile(r'^Channel (?P<channel>%s):\s(?P<handles>.*)$' % r'\d{1,3}')
        re_inchan02 = re.compile(r'(%s)' % icsreg.HANDLE)

        for line in data:
            result=re_inchan01.findall(line)
            if result:
                channel, handles = result[0]
                result=re_inchan02.findall(handles)
                usr = kwargs.get('usr')
                timestamp = time.time()
                compcomm = kwargs.get('compcomm')
                callback = self.whatson_parse_finger

                for handle in result:
                    tsn = self.get_new_tsn()
                    command = 'finger %s' % handle
            
                    trace_logger.debug('(S)->tsn=%d; batchid=%s; compcomm=%s; command=%s' %
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
                trace_logger.debug(line)

        if batchid:
            if not self.track_any_active_trans(batchid):
                self.untrack_batch(batchid)
                if blogger:
                    trace_logger.debug('close log file now..')
                    blogger.close()
        
    def whatson_parse_finger(self, data, args, kwargs):
        trace_logger.debug('in whatson_parse_finger')
        trace_logger.debug('(R)<-%s' % self.format_kwargs(kwargs))

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
                continue
            if re1.match(line):
                message = re1.match(line).group(1)
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
                trace_logger.debug('close log file now..')
                blogger.close()
                
    def do_whatson(self, usr, args, tag):
        """
        For each handle found in channel 177 execute 'finger handle', extract
        some information and show the result in a private tell to the user that
        submitted the 'whatson' command.
        """
        # trace_logger.debug('in do_whatson')
        compcomm = 'whatson'
        f, command, callback, privilege_check = self.get_compcomm_definition(compcomm)
        tsn = self.get_new_tsn()

        trace_logger.debug('(S)->tsn=%d; compcomm=%s; command=%s' %
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

    def timer01(self, run_time):
        repeat = 60 * 60 * 3
        timestamp = time.time()
        self.do_batchrun(me, '-nolog timer1', '')
        self.timer(timestamp + repeat, self.timer01, timestamp + repeat)

    def keep_alive(self, run_time):
        repeat = 60 * 45
        timestamp = time.time()
        self.do_batchrun(me, '-nolog keep_alive', '')
        self.timer(timestamp + repeat, self.keep_alive, timestamp + repeat)

    def do_plusborg(self, usr, args, tag):
        trace_logger.debug('in do_plusborg()')
        trace_logger.debug('usr=%s; args=%s; tag=%s' % (usr, args, tag))
        self.borg_handles.append(args)

    def do_minusborg(self, usr, args, tag):
        trace_logger.debug('in do_minusborg()')
        trace_logger.debug('usr=%s; args=%s; tag=%s' % (usr, args, tag))
        self.borg_handles.remove(args)

    def do_equalsborg(self, usr, args, tag):
        trace_logger.debug('in do_equalsborg()')
        trace_logger.debug('usr=%s; args=%s; tag=%s' % (usr, args, tag))
        self.send('tell %s %s' % (usr, repr(self.borg_handles)))
 
# Main loop in case of disconnections, just recreating the bot right now.
# Should not actually be necessary.
while True:
    if __debug__:
        import instrumentation as instr
        m0 = instr.memory()
        r0 = instr.resident()
        s0 = instr.stacksize()
        
        trace_logger.debug('virtual memory usage  = %d' % m0)
        trace_logger.debug('real memory usage     = %d' % r0)
        trace_logger.debug('stack size            = %d' % s0)

    bot = MCBot(qtell_dummy=True, tell_logger=tell_logger)

    icsbot.status.Status(bot)
    usrs = bot['usrs']

    if __debug__:
        m1 = instr.memory(since=m0)
        r1 = instr.resident(since=r0)
        s1 = instr.stacksize(since=s0)
        
        trace_logger.debug('virtual memory usage increment = %d' % m1)
        trace_logger.debug('real memory usage increment    = %d' % r1)
        trace_logger.debug('stack size increment           = %d' % s1)

    try:
        bot.connect(me, password)
    except icsbot.InvalidLogin, msg:
        if str(msg) == 'Handle in use.':
            trace_logger.error(str(msg), exc_info=True)
            trace_logger.error('Restarting')
            time.sleep(3)
            continue
        trace_logger.critical('Quitting.')
        break
    except icsbot.ConnectionClosed, msg:
        trace_logger.error('Connection was lost.', exc_info=True)
        trace_logger.error('Restarting.')
        time.sleep(3)
        continue
    except icsbot.socket.error, msg:
        trace_logger.error('Socket error.', exc_info=True)
        trace_logger.error('Restarting.')
        time.sleep(3)
        continue
    
    trace_logger.info('Connected to FICS.')

    try:
        bot.run()
    except icsbot.ConnectionClosed, msg:
        if str(msg) == 'Someone logged in as me.':
            trace_logger.critical('Connection was lost because someone logged in as me.')
            trace_logger.critical('Quitting.')
            break
        trace_logger.error('Connection was lost, because:', exc_info=True)
        trace_logger.error('Restarting')
    except icsbot.socket.error, msg:
        trace_logger.error('Socket error:', exc_info=True)
        trace_logger.error('Restarting')

    time.sleep(3)
