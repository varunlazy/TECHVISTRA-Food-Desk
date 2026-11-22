#!/usr/bin/env python3
"""Offline laptop control center. Tkinter is optional; web server needs no GUI."""
import datetime
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser

ROOT=Path(__file__).resolve().parent
PORT=int(os.environ.get('FOODDESK_PORT','8787'))
CUSTOM_HTTPS=bool(os.environ.get('FOODDESK_TLS_CERT') and os.environ.get('FOODDESK_TLS_KEY'))
SETUP_PORT=int(os.environ.get('FOODDESK_SETUP_PORT',str(PORT+1)))
ADMIN_PORT=int(os.environ.get('FOODDESK_ADMIN_PORT',str(PORT+2)))


def main():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox, filedialog
    except ImportError:
        print('Desktop control window is unavailable. Starting the offline web server directly.')
        from server import main as run
        return run()

    from server import local_ips, DB

    root=tk.Tk()
    root.title("TECHVISTRA '26  |  Offline Laptop Server")
    root.geometry('810x740')
    root.minsize(710,560)
    root.configure(bg='#f3f6fc')
    font=('Segoe UI' if sys.platform.startswith('win') else 'Helvetica')
    process=[None]
    launching=[False]

    tk.Frame(root,bg='#132446',height=9).pack(fill='x')
    header=tk.Frame(root,bg='#132446',padx=30,pady=22);header.pack(fill='x')
    tk.Label(header,text="TECHVISTRA '26",font=(font,21,'bold'),fg='white',bg='#132446').pack(anchor='w')
    tk.Label(header,text='OFFLINE FOOD DESK  •  LAPTOP SERVER CONTROL',font=(font,9,'bold'),fg='#a9bdef',bg='#132446').pack(anchor='w',pady=(3,0))

    body=tk.Frame(root,bg='#f3f6fc',padx=25,pady=20);body.pack(fill='both',expand=True)
    connection=tk.Frame(body,bg='white',padx=18,pady=16,highlightbackground='#dae2ed',highlightthickness=1)
    connection.pack(fill='x')
    status=tk.StringVar(value='● Server stopped')
    status_label=tk.Label(connection,textvariable=status,font=(font,15,'bold'),fg='#bb4852',bg='white')
    status_label.pack(anchor='w')
    tk.Label(connection,text='The database stays on this laptop. No cloud or internet connection is used.',
        font=(font,10),fg='#64758c',bg='white').pack(anchor='w',pady=(4,0))

    mode=tk.StringVar(value='lan')  # Phone live QR is the primary event-day use
    modebar=tk.Frame(body,bg='#f3f6fc');modebar.pack(fill='x',pady=(14,2))
    tk.Label(modebar,text='SERVER MODE:',bg='#f3f6fc',fg='#203453',font=(font,10,'bold')).pack(side='left',padx=(0,10))
    radio_laptop=tk.Radiobutton(modebar,text='Laptop only (no network)',variable=mode,value='laptop',bg='#f3f6fc',fg='#203453',selectcolor='white',font=(font,10));radio_laptop.pack(side='left',padx=(0,12))
    radio_lan=tk.Radiobutton(modebar,text='Multiple counters (private Wi-Fi)',variable=mode,value='lan',bg='#f3f6fc',fg='#203453',selectcolor='white',font=(font,10));radio_lan.pack(side='left')
    buttons=tk.Frame(body,bg='#f3f6fc');buttons.pack(fill='x',pady=(15,18))
    def button(parent,text,cmd,color='#fff',fg='#203453'):
        return tk.Button(parent,text=text,command=cmd,bg=color,fg=fg,activebackground='#dddff4',
            bd=0,font=(font,10,'bold'),padx=17,pady=12,cursor='hand2',relief='flat')

    info=tk.Frame(body,bg='white',padx=18,pady=16,highlightbackground='#dae2ed',highlightthickness=1)
    info.pack(fill='x')
    tk.Label(info,text='WHERE TO OPEN THE DASHBOARD',font=(font,10,'bold'),bg='white',fg='#122747').pack(anchor='w')
    address=tk.StringVar()
    tk.Label(info,textvariable=address,font=(font,10),fg='#445776',bg='white',justify='left',anchor='w').pack(fill='x',pady=(9,5))
    tk.Label(info,text='Phone live QR uses trusted HTTPS. Install the public event CA once per phone using Phone HTTPS Setup. Internet is not needed.',
        font=(font,9),fg='#6c7d94',bg='white',wraplength=650,justify='left').pack(anchor='w')

    tk.Label(body,text='EVENT-DAY SERVER LOG',font=(font,10,'bold'),bg='#f3f6fc',fg='#193257').pack(anchor='w',pady=(17,7))
    log=tk.Text(body,height=9,font=('Consolas',9),bg='#0d1a31',fg='#d4e7ff',insertbackground='white',borderwidth=0,padx=13,pady=12)
    log.pack(fill='both',expand=True)
    log.insert('end','TECHVISTRA Offline Food Desk v7.0\nPhone live scanner: Multiple counters + trusted HTTPS.\n')
    log.config(state='disabled')

    def add_log(text):
        if not root.winfo_exists():return
        log.config(state='normal');log.insert('end',text.rstrip()+'\n');log.see('end');log.config(state='disabled')

    def scheme():
        return 'https' if mode.get()=='lan' or CUSTOM_HTTPS else 'http'

    def urls():
        ips=local_ips() if mode.get()=='lan' else []
        lines=[('On this laptop (secure localhost):  http://localhost:'+str(ADMIN_PORT)) if mode.get()=='lan' and not CUSTOM_HTTPS else f'On this laptop:  {scheme()}://localhost:{PORT}']
        if ips:
            lines += [f'Counter phones (LIVE QR):  {scheme()}://{ip}:{PORT}' for ip in ips[:5]]
        else:
            lines.append('Laptop-only selected, or no private Wi-Fi IP available.')
        if ips and not CUSTOM_HTTPS:
            lines.append(f'One-time phone certificate setup:  http://{ips[0]}:{SETUP_PORT}/')
        address.set('\n'.join(lines))
        return ips

    def server_online():
        try:
            with socket.create_connection(('127.0.0.1',PORT),timeout=.2): return True
        except OSError:return False

    def reader(pipe):
        try:
            for line in iter(pipe.readline,''):
                if root.winfo_exists():root.after(0,lambda line=line:add_log(line))
        except (OSError,RuntimeError):pass

    def start():
        if process[0] is not None and process[0].poll() is None:return
        if server_online():
            messagebox.showwarning('Server already active',f'Something is already listening on port {PORT}. Open the dashboard or stop that other server first.')
            return
        try:
            if mode.get() == 'lan' and not CUSTOM_HTTPS:
                from local_https import ensure_certificates
                cert = ensure_certificates(local_ips())
                add_log('Local HTTPS ready. Public CA SHA256: '+cert['fingerprint'])
                if cert['renewed_server']:
                    add_log('Server HTTPS certificate renewed for detected Wi-Fi IPs.')
            flags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith('win') else 0
            env={**os.environ, 'FOODDESK_HOST':'127.0.0.1' if mode.get()=='laptop' else '0.0.0.0'}
            process[0]=subprocess.Popen([sys.executable,'-u',str(ROOT/'server.py')],cwd=ROOT,env=env,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT, text=True,bufsize=1,creationflags=flags)
            threading.Thread(target=reader,args=(process[0].stdout,),daemon=True).start()
            radio_laptop.config(state='disabled');radio_lan.config(state='disabled')
            status.set('● Local server starting…');status_label.config(fg='#ac7017')
            add_log('Starting '+('laptop-only (NO network)' if mode.get()=='laptop' else 'private LAN / phone-counter')+' mode…')
            root.after(400,refresh_status)
        except (OSError, RuntimeError, ValueError) as exc:
            messagebox.showerror('Could not start HTTPS server',str(exc))

    def stop():
        proc=process[0]
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:proc.kill()
            add_log('Stopped server. Saved records remain in the laptop database.')
        process[0]=None
        radio_laptop.config(state='normal');radio_lan.config(state='normal')
        refresh_status()

    def refresh_status():
        urls()
        online=server_online()
        if online:
            status.set('● Server ONLINE — offline-ready')
            status_label.config(fg='#12885d')
        else:
            status.set('● Server stopped')
            status_label.config(fg='#bd4b57')

    def open_dashboard():
        if not server_online():
            messagebox.showinfo('Start server first','Click Start Local Server, then open the admin dashboard.')
            return
        webbrowser.open(f'http://localhost:{ADMIN_PORT}/' if mode.get()=='lan' and not CUSTOM_HTTPS else f'{scheme()}://localhost:{PORT}/')

    def copy_phone():
        ips=urls()
        if not ips:
            messagebox.showinfo('No local Wi-Fi IP','For phone counters, enable a private LAN/hotspot and Refresh IP. For laptop-only scanning, use localhost.')
            return
        url=f'{scheme()}://{ips[0]}:{PORT}'
        root.clipboard_clear();root.clipboard_append(url)
        messagebox.showinfo('Copied local connection URL',url+'\n\nPhone must be on the same private Wi-Fi network.')

    def backup():
        if not DB.exists():
            messagebox.showinfo('No database','Start the server first to create the database.');return
        out=filedialog.asksaveasfilename(defaultextension='.sqlite3',filetypes=[('SQLite backup','*.sqlite3')],
            initialfile='TECHVISTRA_food_backup_'+datetime.date.today().isoformat()+'.sqlite3',title='Save private food desk backup')
        if not out:return
        try:
            src=sqlite3.connect(f'file:{DB.as_posix()}?mode=ro',uri=True)
            dst=sqlite3.connect(out)
            try:src.backup(dst)
            finally:src.close();dst.close()
            add_log('Private database backup saved to '+str(out))
            messagebox.showinfo('Backup saved','Backup complete. This file includes student records and private QR tokens. Keep it secure.')
        except Exception as exc:messagebox.showerror('Backup failed',str(exc))

    b_start=button(buttons,'▶  START LOCAL SERVER',start,color='#176aee',fg='white');b_start.pack(side='left',padx=(0,8))
    button(buttons,'■  Stop',stop).pack(side='left',padx=(0,8))
    button(buttons,'Open Dashboard ↗',open_dashboard).pack(side='left',padx=(0,8))
    extra=tk.Frame(body,bg='#f3f6fc');extra.pack(fill='x',pady=(0,14))
    button(extra,'Copy phone URL',copy_phone).pack(side='left',padx=(0,8))
    button(extra,'↻ Refresh IP',refresh_status).pack(side='left',padx=(0,8))
    button(extra,'↓ Save backup',backup).pack(side='left')

    def phone_https_wizard():
        if mode.get() != 'lan':
            messagebox.showinfo('Select Multiple counters','Switch to Multiple counters (private Wi-Fi) to set up HTTPS phone cameras.')
            return
        if CUSTOM_HTTPS:
            messagebox.showinfo('Custom HTTPS active','You configured custom TLS certificate files. Install and trust their issuing CA on every staff phone.')
            return
        ips=local_ips()
        if not ips:
            messagebox.showwarning('Wi-Fi required','Connect the laptop to the event Wi-Fi or hotspot before preparing phone HTTPS.')
            return
        try:
            from local_https import ensure_certificates, CA_DER
            profile=ensure_certificates(ips)
        except (RuntimeError,OSError,ValueError) as exc:
            messagebox.showerror('Phone HTTPS setup unavailable',str(exc))
            return
        setup=f'http://{ips[0]}:{SETUP_PORT}/'
        scanner=f'https://{ips[0]}:{PORT}/'
        dialog=tk.Toplevel(root)
        dialog.title('Phone HTTPS · TRUST CERTIFICATE · Setup')
        dialog.geometry('670x600')
        dialog.configure(bg='#f3f6fc')
        dialog.transient(root)
        frame=tk.Frame(dialog,bg='#f3f6fc',padx=20,pady=18);frame.pack(fill='both',expand=True)
        tk.Label(frame,text='PHONE LIVE QR • LOCAL HTTPS',font=(font,16,'bold'),fg='#163760',bg='#f3f6fc').pack(anchor='w')
        tk.Label(frame,text='No internet needed during scanning. Every phone must trust the certificate once.',font=(font,10),fg='#536480',bg='#f3f6fc').pack(anchor='w',pady=(5,14))
        def para(txt,fg='#243854',size=10):
            tk.Label(frame,text=txt,wraplength=610,justify='left',anchor='w',font=(font,size),fg=fg,bg='#f3f6fc').pack(fill='x',anchor='w',pady=(0,8))
        para('1. Start Local Server in Multiple counters mode. Connect ALL staff phones and the laptop to the SAME private Wi-Fi.')
        para('2. Open the public setup URL on each phone (no passwords on this HTTP page):')
        para(setup,'#124cbd',11)
        para('3. Download the public certificate. iPhone: Settings → General → VPN & Device Management → Install; then Settings → General → About → Certificate Trust Settings → Enable full trust.')
        para('4. Android: Settings → Security & privacy → Install a certificate → CA certificate (menu names may differ).')
        para('5. Open the HTTPS scanner URL, sign in, tap Start live camera, and grant camera permission:')
        para(scanner,'#124cbd',11)
        para('PUBLIC CA SHA-256 fingerprint — confirm this matches on the phone:',size=9)
        para(profile['fingerprint'],'#7c3366',9)
        para('Do NOT send ca-private.key or server-private.key to phones. Remove the CA trust from staff phones after the event. If the laptop IP changes, restart the server.', '#8c4450', 9)
        commands=tk.Frame(frame,bg='#f3f6fc');commands.pack(fill='x',pady=(8,0))
        def copy(value):
            root.clipboard_clear();root.clipboard_append(value)
            messagebox.showinfo('Copied','Copied to clipboard.',parent=dialog)
        button(commands,'Copy setup URL',lambda:copy(setup),color='#176aee',fg='white').pack(side='left',padx=(0,8))
        button(commands,'Copy HTTPS URL',lambda:copy(scanner)).pack(side='left',padx=(0,8))
        button(commands,'CA fingerprint',lambda:copy(profile['fingerprint'])).pack(side='left')
        cmd2=tk.Frame(frame,bg='#f3f6fc');cmd2.pack(fill='x',pady=(12,0))
        button(cmd2,'Open setup page',lambda:webbrowser.open(setup)).pack(side='left',padx=(0,8))
        button(cmd2,'Show public CA file',lambda:messagebox.showinfo('Public CA certificate',str(CA_DER)+'\nSend ONLY this public .cer certificate to trusted staff phones.',parent=dialog)).pack(side='left')
        dialog.lift()

    button(extra,'🔒 Phone HTTPS Setup',phone_https_wizard,color='#e2ecff',fg='#174f9f').pack(side='left',padx=(8,0))

    def quit():
        if process[0] is not None and process[0].poll() is None:
            if not messagebox.askokcancel('Close offline server?','Stopping this program disconnects every food counter. Continue?'):
                return
            stop()
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',quit)
    mode.trace_add('write',lambda *_:urls())
    urls()
    root.after(500,refresh_status)
    root.mainloop()

if __name__=='__main__':
    main()
