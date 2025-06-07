import seeed_python_reterminal.core as rt
import seeed_python_reterminal.button as rt_btn
import requests
import os
import time

#if os.environ.get('DISPLAY','') == '':
#    print('no display found. Using :0.0')
os.environ.__setitem__('DISPLAY', ':0.0')

import pyautogui

device = rt.get_button_device()
while True:
    for event in device.read_loop():
        buttonEvent = rt_btn.ButtonEvent(event)
        if str(buttonEvent.name) == "ButtonName.F1" and buttonEvent.value == 1:
            requests.post('http://172.16.238.19/backend/venti', json={'cmd':'on','tm':87,'stock':'0'})
            pyautogui.hotkey('f5')
            print(f"Button Ein")
        if str(buttonEvent.name) == "ButtonName.F2" and buttonEvent.value == 1:
            requests.post('http://172.16.238.19/backend/venti', json={'cmd':'off','tm':87,'stock':'0'})
            pyautogui.hotkey('f5')
            print(f"Button Aus")
        if str(buttonEvent.name) == "ButtonName.F3" and buttonEvent.value == 1:
            requests.post('http://172.16.238.19/backend/venti', json={'cmd':'auto','tm':87,'stock':'0'})
            pyautogui.hotkey('f5')
            print(f"Button Auto")
        if str(buttonEvent.name) == "ButtonName.O":
            pyautogui.hotkey('esc')
            off = time.time()
            if buttonEvent.value == 1:
                on = time.time()
            if buttonEvent.value == 0:
                off = time.time()
            duration = off-on
            if duration >0 and duration <= 1:
                pyautogui.hotkey('esc')
                pyautogui.hotkey('f5')
            if duration >= 2:
                 pyautogui.hotkey('esc')
                 print(f"Schutdown")
                 os.system("sudo shutdown now -h")
