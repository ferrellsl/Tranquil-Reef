"""Tranquil Reef Installer: puts the Tranquil Reef screensaver on a Roku.

It walks through turning on the Roku's developer mode, finds Rokus on the
home network, and sends the screensaver channel to the one chosen (the same
upload Roku's own developer web page does).  The developer password is typed
by the user and never stored.

Built into "Tranquil Reef Installer.exe" by build-installer.bat, with the
channel (TranquilReef.zip) inside.
"""
import configparser
import os
import queue
import re
import socket
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.request
import uuid
import webbrowser
import xml.etree.ElementTree as ET
from tkinter import messagebox, ttk

APP = 'Tranquil Reef Installer'
KEPT = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'TranquilReef', 'installer.ini')
HERE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

DEV_MODE_STEPS = (
    "1.  Pick up the Roku remote and press, in order:\n"
    "      Home  Home  Home   Up  Up   Right  Left  Right  Left  Right\n"
    "2.  The Developer Settings screen opens. Choose \"Enable installer and restart\".\n"
    "3.  Accept the developer agreement, then make up a developer password\n"
    "     (write it down: you type it here in a moment).\n"
    "4.  The Roku restarts. Its developer mode stays on until you turn it off\n"
    "     with the same key sequence."
)
AFTER = (
    "To make it your screensaver on the Roku:\n"
    "  Settings  >  Theme  >  Screensavers  >  Tranquil Reef\n"
    "(on some models: Settings > Screensaver).  Choose Preview there to see it\n"
    "at once.  (It is a screensaver only, so it is not on the home screen.)"
)


def channel_zip():
    for p in (os.path.join(HERE, 'TranquilReef.zip'),
              os.path.join(HERE, '..', 'out', 'TranquilReef.zip')):
        if os.path.exists(p):
            return os.path.abspath(p)
    return None


# ------------------------------------------------------------ finding Rokus

def discover(seconds=3.0):
    """SSDP search for Rokus on the local network -> list of IP addresses."""
    msg = ('M-SEARCH * HTTP/1.1\r\nHost: 239.255.255.250:1900\r\nMan: "ssdp:discover"\r\n'
           'ST: roku:ecp\r\nMX: 2\r\n\r\n').encode()
    found = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.settimeout(0.4)
    try:
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        for _ in range(2):
            s.sendto(msg, ('239.255.255.250', 1900))
        import time
        end = time.time() + seconds
        while time.time() < end:
            try:
                data, _ = s.recvfrom(2048)
            except socket.timeout:
                continue
            m = re.search(rb'(?i)location:\s*http://([\d.]+):8060', data)
            if m:
                ip = m.group(1).decode()
                if ip not in found:
                    found.append(ip)
    finally:
        s.close()
    return found


def device_info(ip):
    """The Roku's name, model and whether its developer mode is on."""
    try:
        with urllib.request.urlopen('http://%s:8060/query/device-info' % ip, timeout=3) as r:
            root = ET.fromstring(r.read())
    except (OSError, ET.ParseError):
        return None
    get = lambda tag: (root.findtext(tag) or '').strip()
    name = get('user-device-name') or get('friendly-device-name') or get('default-device-name') or 'Roku'
    return {'ip': ip, 'name': name, 'model': get('model-name'),
            'dev': get('developer-enabled').lower() == 'true'}


# ------------------------------------------------------------ sending

def send(address, user, password, zip_path):
    url = 'http://%s/plugin_install' % address.strip()
    boundary = uuid.uuid4().hex
    with open(zip_path, 'rb') as f:
        archive = f.read()
    body = (('--%s\r\nContent-Disposition: form-data; name="mysubmit"\r\n\r\nInstall\r\n' % boundary).encode()
            + ('--%s\r\nContent-Disposition: form-data; name="archive"; filename="TranquilReef.zip"\r\n'
               'Content-Type: application/zip\r\n\r\n' % boundary).encode()
            + archive + ('\r\n--%s--\r\n' % boundary).encode())
    logins = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    logins.add_password(None, url, user, password)
    opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(logins))
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
    try:
        with opener.open(req, timeout=300) as answer:
            page = answer.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, 'The Roku did not accept the password. It is the developer password you made up when you turned on developer mode.'
        return False, 'The Roku answered with an error (%d %s).' % (e.code, e.reason)
    except (urllib.error.URLError, OSError) as e:
        return False, 'Could not reach the Roku at %s (%s). Is it on, and is developer mode turned on?' % (address, getattr(e, 'reason', e))
    said = []
    for m in re.finditer(r"(Install Success|Identical to previous version[^<']*|Install Failure[^<']*|"
                         r"Application Received[^<']*|Compilation Failed[^<']*)", page):
        if m.group(1) not in said:
            said.append(m.group(1))
    ok = any(x.startswith(('Install Success', 'Identical', 'Application Received')) for x in said)
    return ok, ('Roku: ' + '; '.join(said)) if said else 'Sent. The Roku gave no clear answer; look at the television.'




# ------------------------------------------------------------ the window

class Window:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.devices = []
        root.title(APP)
        root.minsize(720, 640)
        kept = configparser.ConfigParser()
        kept.read(KEPT, encoding='utf-8')
        self.address = tk.StringVar(value=kept.get('installer', 'address', fallback=''))
        self.user = tk.StringVar(value='rokudev')
        self.password = tk.StringVar()

        f = ttk.Frame(root, padding=16)
        f.pack(fill='both', expand=True)
        f.columnconfigure(1, weight=1)
        title = ttk.Label(f, text='Tranquil Reef', font=('Segoe UI', 18, 'bold'))
        title.grid(row=0, column=0, columnspan=3, sticky='w')
        ttk.Label(f, text='A reef aquarium screensaver for Roku').grid(row=1, column=0, columnspan=3, sticky='w', pady=(0, 12))

        step = lambda r, text: ttk.Label(f, text=text, font=('Segoe UI', 11, 'bold')).grid(row=r, column=0, columnspan=3, sticky='w', pady=(10, 4))
        step(2, 'Step 1  -  Turn on developer mode on the Roku')
        ttk.Label(f, text=DEV_MODE_STEPS, justify='left').grid(row=3, column=0, columnspan=3, sticky='w', padx=(8, 0))
        ttk.Label(f, text='Developer mode only lets you install channels from your own computer; '
                          'it does not change anything else on the Roku. A Roku keeps one channel installed '
                          'this way at a time, so this replaces any other one you put on it like this.', foreground='#555',
                  wraplength=660).grid(row=4, column=0, columnspan=3, sticky='w', padx=(8, 0), pady=(4, 0))

        step(5, 'Step 2  -  Choose your Roku')
        self.listbox = tk.Listbox(f, height=4, activestyle='none')
        self.listbox.grid(row=6, column=0, columnspan=2, sticky='ew', padx=(8, 0))
        self.listbox.bind('<<ListboxSelect>>', self.picked)
        self.find_btn = ttk.Button(f, text='Find Rokus', command=self.find)
        self.find_btn.grid(row=6, column=2, sticky='n', padx=(8, 0))
        ttk.Label(f, text='Address').grid(row=7, column=0, sticky='w', padx=(8, 0), pady=(6, 0))
        ttk.Entry(f, textvariable=self.address).grid(row=7, column=1, sticky='ew', pady=(6, 0))
        ttk.Label(f, text='(found automatically, or type it: Settings > Network > About on the Roku)',
                  foreground='#555').grid(row=8, column=1, sticky='w')

        step(9, 'Step 3  -  Install')
        ttk.Label(f, text='Developer password').grid(row=10, column=0, sticky='w', padx=(8, 0))
        ttk.Entry(f, textvariable=self.password, show='•').grid(row=10, column=1, sticky='ew')
        self.install_btn = ttk.Button(f, text='Install Tranquil Reef', command=self.install)
        self.install_btn.grid(row=10, column=2, padx=(8, 0))

        self.log = tk.Text(f, height=9, wrap='word', state='disabled', font=('Segoe UI', 9))
        self.log.grid(row=11, column=0, columnspan=3, sticky='nsew', pady=(12, 0))
        f.rowconfigure(11, weight=1)
        self.say('Follow the steps from the top. The password is used only to send the screensaver and is never saved.\n')
        if not channel_zip():
            self.say('\nThe screensaver file (TranquilReef.zip) is missing from this installer.\n')
        root.after(100, self.poll)
        root.after(300, self.find)

    def say(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text)
        self.log.see('end')
        self.log.configure(state='disabled')

    def find(self):
        self.find_btn.configure(state='disabled')
        self.say('\nLooking for Rokus on your network...\n')

        def work():
            ips = discover()
            infos = [i for i in (device_info(ip) for ip in ips) if i]
            self.q.put(('found', infos))
        threading.Thread(target=work, daemon=True).start()

    def picked(self, _=None):
        sel = self.listbox.curselection()
        if sel and sel[0] < len(self.devices):
            self.address.set(self.devices[sel[0]]['ip'])

    def install(self):
        zp = channel_zip()
        addr = self.address.get().strip()
        if not zp:
            messagebox.showerror(APP, 'The screensaver file is missing from this installer.')
            return
        if not addr:
            messagebox.showinfo(APP, 'Choose your Roku (Step 2) first.')
            return
        if not self.password.get():
            messagebox.showinfo(APP, 'Type the developer password you made up in Step 1.')
            return
        self.install_btn.configure(state='disabled')
        self.say('\nSending Tranquil Reef to %s (%.0f MB, this takes a minute)...\n' % (addr, os.path.getsize(zp) / 1e6))
        user, pw = self.user.get(), self.password.get()

        def work():
            ok, text = send(addr, user, pw, zp)
            self.q.put(('sent', (ok, text, addr)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == 'found':
                    self.devices = val
                    self.listbox.delete(0, 'end')
                    for d in val:
                        flag = '' if d['dev'] else '   (developer mode is off)'
                        self.listbox.insert('end', '%s  -  %s  -  %s%s' % (d['name'], d['model'], d['ip'], flag))
                    if val:
                        self.say('Found %d Roku%s. Pick yours in the list.\n' % (len(val), '' if len(val) == 1 else 's'))
                        if len(val) == 1 or not self.address.get():
                            self.listbox.selection_set(0)
                            self.picked()
                    else:
                        self.say('No Roku answered. Check that this computer is on the same network as the Roku, '
                                 'or type its address.\n')
                    self.find_btn.configure(state='normal')
                elif kind == 'sent':
                    ok, text, addr = val
                    self.say(text + '\n')
                    self.install_btn.configure(state='normal')
                    if ok:
                        self.keep(addr)
                        self.say('\nInstalled.\n' + AFTER + '\n')
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def keep(self, addr):
        kept = configparser.ConfigParser()
        kept['installer'] = {'address': addr}
        os.makedirs(os.path.dirname(KEPT), exist_ok=True)
        with open(KEPT, 'w', encoding='utf-8') as f:
            kept.write(f)


def main():
    root = tk.Tk()
    try:
        root.iconbitmap(default=os.path.join(HERE, 'tranquil_reef.ico'))
    except tk.TclError:
        pass
    Window(root)
    root.mainloop()


if __name__ == '__main__':
    main()
