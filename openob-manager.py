#!/usr/bin/env python
# OpenOB Link Manager
# One of these runs at each end and negotiates everything (RX pushes config info to TX), reconnects when links fail, and so on.
import sys
import time
import argparse
import redis
# Thanks gst for messing with argv
argv = sys.argv
sys.argv = []
from openob.rtp.tx import RTPTransmitter
from openob.rtp.rx import RTPReceiver
sys.argv = argv

class Manager:
  '''OpenOB Manager. Handles management of links, mostly recovery from failures.'''
  def run(self, opts):
    print("-- OpenOB Audio Link")
    print(" -- Starting Up")
    print(" -- Parameters: %s" % opts)
    # We're now entering the realm where we should desperately try and maintain a link under all circumstances forever.
    while True:
      try:
        # Set up redis and connect
        config = None
        while True:
          try:
            config = redis.Redis(opts.config_host)
            print(" -- Connected to configuration server")
            break
          except Exception, e:
            print(" -- Couldn't connect to Redis! Ensure your configuration host is set properly, and you can connect to the default Redis port on that host from here (%s)." % e)
            print("    Waiting half a second and attempting to connect again.")
            time.sleep(0.5)

        # So if we're a transmitter, let's set the options the receiver needs to know about
        link_key = "openob2:"+opts.link_name+":"
        if opts.mode == 'tx':
          # We're a transmitter!
          config.set(link_key+"port", opts.port)
          config.set(link_key+"jitter_buffer", opts.jitter_buffer)
          config.set(link_key+"encoding", opts.encoding)
          config.set(link_key+"bitrate", opts.bitrate)
          print(" -- Configured receiver with:")
          print("   - Base Port:     %s" % config.get(link_key+"port"))
          print("   - Jitter Buffer: %s ms" % config.get(link_key+"jitter_buffer"))
          print("   - Encoding:      %s" % config.get(link_key+"encoding"))
          print("   - Bitrate:       %s kbit/s" % config.get(link_key+"bitrate"))
          # Okay, we can't set caps yet - we need to configure ourselves first.
          transmitter = RTPTransmitter(audio_input=opts.audio_input, audio_device=opts.device, base_port=opts.port, encoding=opts.encoding, bitrate=opts.bitrate, jack_name=("openob_tx_%s" % opts.link_name), receiver_address=opts.receiver_host)
          # Set it up, get caps
          try:
            transmitter.run()
            config.set(link_key+"caps", transmitter.get_caps())
            print("   - Caps:          %s" % config.get(link_key+"caps"))
            transmitter.loop()
          except Exception, e:
            print(" -- Lost connection or otherwise had the transmitter fail on us, restarting (%s)" % e)
            time.sleep(0.5)
        else:
          # We're a receiver!
          # Default values.
          port = 3000
          caps = ''
          jitter_buffer = 150
          encoding = 'opus'
          bitrate = '96'
          while True:
            try:
              if config.get(link_key+"port") == None:
                print(" -- Unable to configure myself from the configuration host; has the transmitter been started yet, and have you got the same link name on each end?")
                print("    Waiting half a second and attempting to reconfigure myself.")
                time.sleep(0.5)
              port = int(config.get(link_key+"port"))
              caps = config.get(link_key+"caps")
              jitter_buffer = int(config.get(link_key+"jitter_buffer"))
              encoding = config.get(link_key+"encoding")
              bitrate = int(config.get(link_key+"bitrate"))
              print(" -- Configured from transmitter with:")
              print("   - Base Port:     %s" % port)
              print("   - Jitter Buffer: %s ms" % caps)
              print("   - Encoding:      %s" % encoding)
              print("   - Bitrate:       %s kbit/s" % bitrate)
              print("   - Caps:          %s" % caps)
              break
            except Exception, e:
              print(" -- Unable to configure myself from the configuration host; has the transmitter been started yet? (%s)" % e)
              print("    Waiting half a second and attempting to reconfigure myself.")
              time.sleep(0.5)
              #raise
          # Okay, we can now configure ourself
          receiver = RTPReceiver(audio_output=opts.audio_output, audio_device=opts.device, base_port=port, encoding=encoding, caps=caps, bitrate=bitrate, jitter_buffer=jitter_buffer, jack_name=("openob_tx_%s" % opts.link_name) )
          try:
            receiver.run()
            receiver.loop()
          except Exception, e:
            print(" -- Lost connection or otherwise had the receiver fail on us, restarting (%s)" % e)
            time.sleep(0.5)

      except Exception, e:
        print(" -- Unhandled exception occured, please report this as a bug!")
        raise

if __name__ == '__main__':
  parser = argparse.ArgumentParser(prog='openob-manager',version='openob-manager 0.9')
  parser.add_argument('config_host', type=str, help="The configuration server for this OpenOB Manager")
  parser.add_argument('link_name', type=str, help="The link name this OpenOB Manager is operating on; must be the same on both Managers")
  subparsers = parser.add_subparsers(help="The link mode to operate in on this end")
  parser_tx = subparsers.add_parser('tx')
  parser_tx.add_argument('receiver_host', type=str, help="The receiver for this transmitter. The machine at this address must be running an rx-mode Manager for this link name")
  parser_tx.add_argument('-a', '--audio_input', type=str, choices=['alsa', 'jack', 'pulseaudio'], default='alsa', help="The audio source type for this end of the link")
  parser_tx.add_argument('-d', '--device', type=str, default='hw:0', help="The ALSA audio device when in ALSA audio input mode")
  parser_tx.add_argument('-e', '--encoding', type=str, choices=['pcm','celt','opus'], default='opus', help="The audio encoding type for this link; PCM for linear audio (16-bit), CELT or Opus (default) for encoded audio")
  parser_tx.add_argument('-b', '--bitrate', type=int, default=96, help="Bitrate if using CELT/Opus (in kbit/s)", choices=[16,24,32,48,64,96,128])
  parser_tx.add_argument('-p', '--port', type=int, default=3000, help="The base port to use for audio transport. This port must be accessible on the receiving host")
  parser_tx.add_argument('-j', '--jitter_buffer', type=int, default=150, help="The size of the jitter buffer in milliseconds. Affects latency; may be reduced to 5-10ms on fast reliable networks, or increased for poor networks like 3G")
  parser_tx.set_defaults(mode='tx')
  parser_rx = subparsers.add_parser('rx')
  parser_rx.add_argument('-a', '--audio_output', type=str, choices=['alsa', 'jack', 'pulseaudio'], default='alsa', help="The audio output type for this end of the link")
  parser_rx.add_argument('-d', '--device', type=str, default='hw:0', help="The ALSA audio device when in ALSA audio output mode")
  parser_rx.set_defaults(mode='rx')
  opts = parser.parse_args()
  manager = Manager()
  manager.run(opts)
