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

import getopt

import copy

__usage__ = """
To start mcbot:
in linux:
   from the directory where you installed mcbot:
          python [-OO] ./mcbot.py [-h|--help] [-t|--testing]
                 -OO : no debugging
                 without -OO debugging info is logged in ./mcbot.log
                 -t|--testing: use test login data from logintestdata.py
in windows:
   dunno, don't care
"""

def usage():
    print __usage__

# handle command line options
try:
    opts, args = getopt.getopt(sys.argv[1:], "ht", ["help", "testing"])
except getopt.GetoptError, err:
    # print help information and exit:
    print str(err) # will print something like "option -a not recognized"
    usage()
    sys.exit(2)
testing = False
for o, a in opts:
    if o in ("-t", "--testing"):
        testing = True
    elif o in ("-h", "--help"):
        usage()
        sys.exit()
    else:
        assert False, "unhandled option"
        
if testing:
    from logintestdata import me, password, admin, finger_text
else:
    from logindata import me, password, admin, finger_text 

re_empty = re.compile("^(\s|\r|\n|\t)*$")
def is_empty(text):
    """
    """
    return re_empty.match(text) and True or False
    
tells_file = file('tell.log', 'a')
def tell_logger(tell):
    tells_file.write(time.strftime('%d-%m %H:%M: ', time.localtime()) + ': ' +  tell)
    tells_file.flush()

class Log(object):
    def __init__(self, location):
        self.buf = ''
        self.errors = file(location, 'a')
    
    def write(self, output):
        out = str(output).split('\n')
        out[0] = self.buf + out[0]
        self.buf = out[-1]
        for spam in out[:-1]:
            self.errors.write(time.strftime('\n%d-%m %H:%M: ', time.localtime()) +  str(spam))
        self.errors.flush()

    def close(self):
        self.errors.flush()
        self.errors.close()

errors = Log('mcbot.log')

sys.stderr = errors
# sys.stdout = errors

def printerr(msg):
    if __debug__:
        sys.stderr.write(msg + '\n')

if __debug__:
    import instrumentation as instr

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
                         lambda usr, tags: True)
            }
        # send pre-login commands
        self.send('set style 12')
        self.send('set seek 0')
        self.send('set interface MonkeyClub Bot(mcbot)')
        # bot.send('tell 177 Remember to "set noescape 0" before you start a tl game..')
        # bot.send('tell 177 or you risk forfeit by disconnection.')

        self.reg_comm('(?P<usr>[a-zA-Z]{3,17})(?:\([A-Z]+\))*\((?P<channel>[0-9]{1,3})\): (?P<message>.*)', self.respond_channel_tell)

        self.reg_comm('(?P<usr>[a-zA-Z]{3,17})(?:\([A-Z]+\))*\: (?P<message>.*)', self.respond_personal_tell)

        # register bot commands
        for key, (method, command, callback, privilege_check) in self._compcomms.iteritems():
            self.reg_tell(key, method, privilege_check)
        
        # timed commands
        t = time.time()
        self.timer(t + 60 * 60, self.timer01, t)

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

    def respond_channel_tell(self, matches):
        printerr(' > respond_channel_tell')
        usr = matches.group('usr')
        channel = matches.group('channel')
        message = matches.group('message')
        printerr('usr = %s; channel = %s; message = %s' % (usr, channel, message))
        # return 'tell %s %s' % (admin, matches.group(0))
        return None

    def respond_personal_tell(self, matches):
        printerr(' > respond_personal_tell')
        usr = matches.group('usr')
        message = matches.group('message')
        # printerr('usr = %s; message = %s' % (usr, message))
        # return 'tell %s %s' % (admin, matches.group(0))
        return None

    def handle_response(self, data, args, kwargs):
        printerr(' > handle_response')
        printerr('(R)<-tsn=%d; batchrun=%s; compcomm=%s; command=%s' %
                 (kwargs.get('tsn'), kwargs.get('batchrun', 'No'),
                  kwargs.get('compcomm', 'No'),
                  kwargs.get('command')
                  ))
        # printerr('kwargs = %s' % (repr(kwargs)))
        # printerr('data = %s' % (repr(data)))
        if kwargs.get('callback'):
            kwargs.get('callback')(data, args, kwargs)
        else:
            if kwargs.get('batchrun'):
                # assert kwargs.get('blogger')
                data = data.split('\n\r')
                # printerr('data = %s' % repr(data))
                for line in data:
                    if kwargs['blogger']:
                        kwargs['blogger'].write('%s\n' % line)
                    else:
                        pass
                        # self.send('tell %s %s' % ('177', line))
                # if kwargs.get('last'):
                #     kwargs['blogger'].close()
                    
        printerr('---')

    def submit_batch_commands(self, lines, usr, blogger):
        printerr(' > submit_batch_commands')

        count = 0
        for index, item in enumerate(lines):
            args=None
            kwargs=dict(
                batchrun = True,
                usr = str(usr),
                tsn = self.get_new_tsn(),
                timestamp = time.time(),
                command = item,
                blogger = blogger
                )
            command = item.split()[0]
            if self.is_compcomm(command):
                method, command, callback, privilege_check = self.get_compcomm_definition(command)
                kwargs['compcomm'] = item
                kwargs['command'] = command
                kwargs['callback'] = callback
            printerr('submit %s' % item)
            if blogger:
                blogger.write('submit %s\n' % kwargs['command'])

            printerr('(S)->tsn=%d; batchrun=%s; compcomm=%s; command=%s' %
                     (kwargs.get('tsn'), kwargs.get('batchrun', 'No'),
                      kwargs.get('compcomm', 'No'),
                      kwargs.get('command')
                      ))
            self.execute(kwargs['command'], self.handle_response, args, kwargs)

    def handle_batch_file(self, filename, usr):
        """
        """
        # printerr("reading commands from file '%s'" % filename)
        printerr(' > handle_batch_file')
        try: 
            f = None
            f = open(filename, 'rU')
            if filename.startswith('timer'):
                blogger = None
            else:
                blogger = Log(filename + '.log')
                blogger.write('reading commands from file \'%s\'\n' % filename)
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
        Usage: batchrun file [file..]
        Executes all fics commands in 'file' in batch, and logs
        the results in file.log
        """
        printerr(' > do_batchrun')
        # printerr('usr = %s%s; command = %s %s' % 
        #          (str(usr).lower(), str(tag), 'batchrun', str(args)))
        
        arglist=str(args).split()
        if len(arglist) == 0:
            printerr('** Usage: batchrun file [file...]')
        else:
            for filename in arglist:
                self.handle_batch_file(filename, str(usr))
                printerr("-----")

    def whatson_parse_inchannel(self, data, args, kwargs):
        printerr(' > whatson_parse_inchannel')
        printerr('(R)<-tsn=%d; batchrun=%s; compcomm=%s; command=%s' %
                 (kwargs.get('tsn'), kwargs.get('batchrun', 'No'),
                  kwargs.get('compcomm', 'No'),
                  kwargs.get('command')
                  ))
        data = data.split('\n\r')
        # printerr('number of lines: %d' % (len(data)))
        for line in data:
            printerr(line)
        re_inchan01 = re.compile('^Channel (?P<channel>[0-9]{1,3}):\s(?P<handles>.*)$')
        re_inchan02 = re.compile('([a-zA-Z]{3,17})')
        for line in data:
            result=re_inchan01.findall(line)
            if result:
                printerr('result = %s' % repr(result))
                channel, handles = result[0]
                result=re_inchan02.findall(handles)
                printerr('channel = %s' % (channel))
                printerr('handles = %s' % repr(result))
                usr = kwargs.get('usr')
                batchrun = kwargs.get('batchrun')
                timestamp = time.time()
                compcomm = kwargs.get('compcomm')
                callback = self.whatson_parse_finger
                for handle in result:
                    tsn = self.get_new_tsn()
                    command = 'finger %s' % handle
            
                    printerr('(S)->tsn=%d; batchrun=%s; compcomm=%s; command=%s' %
                             (tsn, batchrun, compcomm, command))

                    self.execute(command, 
                                 self.whatson_parse_finger, 
                                 [],
                                 {'usr': usr,
                                  'tsn': tsn,
                                  'timestamp': timestamp,
                                  'compcomm': compcomm,
                                  'command': command,
                                  'callback': callback
                                  })
            # else:
            #     re_inchan03 = re.compile('[0-9]+ players are in channel %s.' % (channel))
            #     result = re_inchan03.match(line)
            #     if result:
            #         printerr(line)

    def whatson_parse_finger(self, data, args, kwargs):
        printerr(' > whatson_parse_finger')
        printerr('(R)<-tsn=%d; batchrun=%s; compcomm=%s; command=%s' %
                 (kwargs.get('tsn'), kwargs.get('batchrun', 'No'),
                  kwargs.get('compcomm', 'No'),
                  kwargs.get('command')
                  ))
        data = data.split('\n\r')
        # printerr('number of lines: %d' % (len(data)))
        # for line in data:
        #     printerr(line)
        re1 = re.compile('\((.*)\)')
        re2 = re.compile('\s+rating')
        re3 = re.compile('^Finger of ([a-zA-Z]{3,17})(.*):')
        status = None
        for line in data:
            # print 'line = %s' % line
            if re_empty.match(line):
                continue
            if re3.match(line):
                handle = re3.match(line).group(1)
                # print 'handle = %s' % handle
                continue
            if re1.match(line):
                status = re1.match(line).group(1)
                # print 'status = %s' % status
                break
            if re2.match(line):
                break
        if status:
            if not status.startswith('%s is ' % handle):
                status = '%s is %s' % (handle, status)
            # self._bot.send('tell %s %s' % (kwargs['usr'], status))
            if kwargs.get('batchrun'):
                assert kwargs.get('blogger')
                kwargs.get('blogger').write(status)
            else:
                self.send('tell %s %s' % (kwargs.get('usr'), status))
                
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
        batchrun = 'N'

        printerr('(S)->tsn=%d; batchrun=%s; compcomm=%s; command=%s' %
                 (tsn, batchrun, compcomm, command))

        self.execute(command, 
                     self.handle_response, 
                     [], 
                     {'usr': str(usr),
                      'tsn': tsn,
                      'timestamp': time.time(),
                      'compcom': compcomm,
                      'command': command,
                      'callback': callback
                      })

        printerr("-----")

    def timer01_callback(self, data, args, kwargs):
        printerr(' > timer01_callback')
        printerr('(R)<-tsn=%d; batchrun=%s; compcomm=%s; command=%s' %
                 (kwargs.get('tsn'), kwargs.get('batchrun', 'No'),
                  kwargs.get('compcomm', 'No'),
                  kwargs.get('command')
                  ))

        data = data.split('\n\r')
        for line in data:
            printerr('%s' % line)
        re1 = re.compile('linuxchick tells you: (.*)')
        for line in data:
            if re_empty.match(line):
                continue
            if re1.match(line):
                command = re1.match(line).group(1)
                break
            
        tokens = command.split()
            
        if tokens[0] == 'batchrun':
            self.do_batchrun(kwargs.get('usr'), ' '.join(tokens[1:]), '') 

    def timer01(self, run_time):
        printerr(' > timer01')
        repeat = 60 * 30
        tsn = self.get_new_tsn()
        timestamp = time.time()
        command = 'tell %s batchrun timer1' % me
        compcomm = 'N'
        batchrun = 'N'

        printerr('(S)->tsn=%d; batchrun=%s; compcomm=%s; command=%s' %
                 (tsn, batchrun, compcomm, command))

        self.execute(command, 
                     self.timer01_callback, 
                     [], 
                     {'usr': me, 
                      'tsn': tsn, 
                      'timestamp': time.time(), 
                      'blogger': None,
                      'command': command
                      })

        self.timer(run_time + repeat, self.timer01, run_time + repeat)
 
# Main loop in case of disconnections, just recreating the bot right now.
# Should not actually be necessary.
while True:
    if __debug__:
        m0 = instr.memory()
        r0 = instr.resident()
        s0 = instr.stacksize()

    bot = MCBot(qtell_dummy=True, tell_logger=tell_logger)

    # 
    icsbot.status.Status(bot)
    usrs = bot['usrs']

    if __debug__:
        m1 = instr.memory(since=m0)
        r1 = instr.resident(since=r0)
        s1 = instr.stacksize(since=s0)
        
        printerr('vitual memory usage increment = %d' % m1)
        printerr('real memory usag increment = %d' % r1)
        printerr('stack size increment = %d' % s1)

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
