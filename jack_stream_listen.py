import sys
import json

# this might be a problem with tkinter...
import threading

try:
    from tkinter import *
    import tkinter as ttk
except:
    try:
        from Tkinter import *
        import Tkinter as ttk
    except:
        print('ERROR: Unable to import GUI package, tkinter or Tkinter')
        print('ERROR: This should come included with your Python install')
        sys.exit(0)
try:
    import sounddevice as sd
except:
    print('ERROR: Unable to import audio package, sounddevice')
    print('ERROR: Please install sounddevice by running')
    print('ERROR:     pip install sounddevice')
    sys.exit(0)

root = Tk()
root.title("JACK Stream Listener")

# Add a grid
mainframe = Frame(root)
mainframe.grid(column=0,row=0, sticky=(N,W,E,S) )
mainframe.columnconfigure(0, weight = 1)
mainframe.rowconfigure(0, weight = 1)
mainframe.pack(pady = 100, padx = 100)

# Create a Tkinter variables
play_dev_str = StringVar(root)
ip_str = StringVar(root)
port_str = StringVar(root)

# get sounddevice list
dev_list = sd.query_devices()

# filter to only use playback devices
play_devs = [json.dumps((idx,dev_list[idx]['name'])) 
                for idx in range(len(dev_list))
                   if dev_list[idx]['max_output_channels'] > 0]

# Choose playback device
play_dev_str.set('Please Choose Playback Device') # set the default option
play_menu = OptionMenu(mainframe, play_dev_str, *play_devs)
Label(mainframe, text='Playback Devicex').grid(row = 0, column = 0)
play_menu.grid(row = 0, column =1)

# Create playback device dropdown listener function
chosen_dev = None
def change_playback_dropdown(*args):
    chosen_dev = json.loads(play_dev_str.get())
    print('Selected device {} with name = {}'.format(
        chosen_dev[0], chosen_dev[1]))
    # FIXME, connect and create stream now, or at socket connection time?

# Link function to change dropdown
play_dev_str.trace('w', change_playback_dropdown)

# Create Labels and Entries for ip/port
Label(mainframe, text="IP Address").grid(row=4, column=0)
Label(mainframe, text="Port").grid(row=5, column=0)
ip_entry = Entry(mainframe).grid(row=4, column=1)
port_entry = Entry(mainframe).grid(row=5, column=1)

# Create connection handler, FIXME lots TODO here
def handle_connection(*args):
    
    Label(mainframe, text="Neato").grid(row=10, column=0)
    Label(mainframe, text="Mosquito").grid(row=11, column=0)
    print('Cool Ranch Doritos!')

# Create connection button
connect_button = Button(
    mainframe, text="Connect", 
    fg="white", bg="purple",
    command=handle_connection).grid(row=7, column=1)




root.mainloop()