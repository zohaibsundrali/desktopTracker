"""Render real login widgets with inert providers; check responsive layout and callbacks."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with patch.dict(sys.modules, {'auth_manager':SimpleNamespace(AuthManager=Mock),
        'ui_dashboard':SimpleNamespace(DashboardWindow=Mock),
        'notification_popup':SimpleNamespace(set_notification_root=Mock)}):
    import ui_login
    import customtkinter as ctk
    from PIL import ImageGrab
    with patch.object(ui_login.LoginWindow,'_load_saved_credentials'):
        login=ui_login.LoginWindow()
        errors=[]
        login.app.report_callback_exception=lambda *args:errors.append(args)
        try:
            for scale,width,height in [(1,900,640),(1,480,640),(1.25,900,640),(1.5,480,640)]:
                ctk.set_widget_scaling(scale)
                ctk.set_window_scaling(scale)
                from tkinter import BooleanVar
                settled=BooleanVar(master=login.app,value=False)
                login.app.after(1200,lambda:settled.set(True))
                login.app.wait_variable(settled)
                login.app.geometry(f'{width}x{height}+0+0')
                login.app.update()
                login.app.after(150)
                login.app.update()
                print("layout",scale,width,login.app.winfo_width(),login._login_root.winfo_width(),login._login_root._get_widget_scaling(),login._compact,flush=True)
                assert login._compact == (width<780)
                for widget in [login.email_input,login.pass_input,login.signin_button,
                               login.forgot_button,login.register_button,login.remember_check]:
                    assert widget.winfo_viewable()
                    assert widget.winfo_rootx() >= login.app.winfo_rootx()
                    assert widget.winfo_rootx()+widget.winfo_width() <= login.app.winfo_rootx()+login.app.winfo_width()
                    assert widget.winfo_rooty()+widget.winfo_height() <= login.app.winfo_rooty()+login.app.winfo_height()
                if scale==1:
                    out=Path('Output/login-preview');out.mkdir(parents=True,exist_ok=True)
                    x,y=login.app.winfo_rootx(),login.app.winfo_rooty()
                    ImageGrab.grab().crop((x,y,x+login.app.winfo_width(),y+login.app.winfo_height())).save(out/f'login-{width}.png')
            with patch.object(login,'login') as authenticate:
                login._submit_login()
                authenticate.assert_called_once()
                assert login.signin_button.cget('state')=='normal'
            with patch('ui_login.messagebox.showinfo') as info:
                login.forgot_button.invoke();login.register_button.invoke()
                assert info.call_count==2
            assert not errors,errors
            print('Login wide/narrow layouts, 100/125/150% scaling, submit and existing actions passed.')
        finally:
            login.app.destroy()
