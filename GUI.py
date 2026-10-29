#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
import sys, time, cardReaderExceptions, cardReader
from tkinter import *
from tkinter import ttk
from tkinter.messagebox import *
from tkinter import filedialog
import sqlite3


class GUI(Frame):    
    def __init__(self, parent):
        Frame.__init__(self, parent)
        
        self.__coercivityRadioBtnValue = StringVar()
        self.__coercivityRadioBtnValue.set('hi')
        
        self.__autoSaveDatabase = BooleanVar()
        self.__autoSaveDatabase.set(False)
        
        self.__enableDuplicates = BooleanVar()
        self.__enableDuplicates.set(False)
        
        self.__connected = False        
        self.__connectedLabelIndicator = None
        
        self.__tracks = ['', '', '']
        self.__trackOneEntry = None
        self.__trackTwoEntry = None
        self.__trackThreeEntry = None        
        
        self.__msr = None
        
        self.build_main_window()
        

    def main_window_menu(self):
        m = Menu(root)
    
        fileMenu = Menu(m, tearoff=0)
        fileMenu.add("command", label="退出 (Exit)", command=self.on_exit)
            
        m.add("cascade", menu=fileMenu, label="文件")
        
        databaseMenu = Menu(m, tearoff=0)
        databaseMenu.add("command", label="查看已保存卡片", command=self.view_database)
        databaseMenu.add("checkbutton", label="读卡后自动保存到数据库", onvalue=True, offvalue=False, variable=self.__autoSaveDatabase)
        databaseMenu.add("checkbutton", label="允许保存重复卡片", onvalue=True, offvalue=False, variable=self.__enableDuplicates)
            
        m.add("cascade", menu=databaseMenu, label="数据库")
        
        root.configure(menu=m)
        
        
    def build_main_window(self):
        # 顶部菜单
        self.main_window_menu()
          
        # 左侧磁道数据显示区
        tracks = Frame(root)     
        tracks.pack(side=LEFT, padx=15, pady=10)
        
        # 磁道 1
        trackOneFrame = Frame(tracks, padx=5, pady=5)     
        trackOneFrame.grid(row=0, column=0, sticky='w')       
        Label(trackOneFrame, text="第 1 磁道\n(Track 1)", padx=5, pady=5, font=('微软雅黑', 9, 'bold')).pack(side=LEFT)    
        self.__trackOneEntry = Text(trackOneFrame, bd=1, width=52, height=3, font=('Consolas', 10))
        self.__trackOneEntry.pack(side=RIGHT)
        
        # 磁道 2 (超市会员卡最核心的卡号磁道)
        trackTwoFrame = Frame(tracks, padx=5, pady=5)     
        trackTwoFrame.grid(row=1, column=0, sticky='w')       
        Label(trackTwoFrame, text="第 2 磁道\n(会员卡号)", padx=5, pady=5, font=('微软雅黑', 9, 'bold'), fg='#0066cc').pack(side=LEFT)    
        self.__trackTwoEntry = Text(trackTwoFrame, bd=1, width=52, height=3, font=('Consolas', 10))
        self.__trackTwoEntry.pack(side=RIGHT)
        
        # 磁道 3
        trackThreeFrame = Frame(tracks, padx=5, pady=5)   
        trackThreeFrame.grid(row=2, column=0, sticky='w')     
        Label(trackThreeFrame, text="第 3 磁道\n(Track 3)", padx=5, pady=5, font=('微软雅黑', 9, 'bold')).pack(side=LEFT)    
        self.__trackThreeEntry = Text(trackThreeFrame, bd=1, width=52, height=3, font=('Consolas', 10))
        self.__trackThreeEntry.pack(side=RIGHT)
        
        # 连接状态提示标签
        self.__connectedLabelIndicator = Label(
            tracks,
            text="● 设备未连接",
            fg='red',
            padx=10,
            pady=12,
            font=('微软雅黑', 13, 'bold')
        )
        self.__connectedLabelIndicator.grid(row=3, column=0)     
        
        # 设备连接与复位控制按钮
        btn_frame = Frame(tracks)
        btn_frame.grid(row=4, column=0, pady=5)
        Button(btn_frame, text="🔌 连接读写器", width=15, height=1, font=('微软雅黑', 9), command=self.connect_to_msr605).pack(side=LEFT, padx=5)
        Button(btn_frame, text="❌ 断开连接", width=15, height=1, font=('微软雅黑', 9), command=self.close_connection).pack(side=LEFT, padx=5)
        Button(btn_frame, text="🔄 复位设备", width=15, height=1, font=('微软雅黑', 9), command=self.reset).pack(side=LEFT, padx=5)
        
        # 右侧操作面板
        buttons = Frame(root)     
        buttons.pack(side=RIGHT, padx=15, pady=10, fill=Y)
        
        # 读卡 / 写卡 / 擦除核心操作按钮组
        readWriteEraseButtons = Frame(buttons, padx=10, pady=5)
        readWriteEraseButtons.pack(side=TOP, padx=10, fill=X)
        Label(readWriteEraseButtons, text="【 会员卡操作 】", font=('微软雅黑', 10, 'bold'), fg='#333').pack(side=TOP, pady=3)    
        Button(readWriteEraseButtons, text="▶ 开始读卡 (READ)", bg='#e6f4ea', fg='#137333', font=('微软雅黑', 10, 'bold'), height=2, command=self.read_card).pack(side=TOP, fill=X, pady=3)
        Button(readWriteEraseButtons, text="✍ 写入卡片 (WRITE)", bg='#fce8e6', fg='#c5221f', font=('微软雅黑', 10, 'bold'), height=2, command=self.write_card).pack(side=TOP, fill=X, pady=3)
        Button(readWriteEraseButtons, text="✖ 擦除卡片 (ERASE)", font=('微软雅黑', 9), command=self.erase_card).pack(side=TOP, fill=X, pady=3)

        # 抗磁性单选框 (Coercivity)
        coercivityRadioButtons = Frame(buttons, padx=10, pady=5)
        coercivityRadioButtons.pack(side=TOP, padx=10, fill=X)
        Label(coercivityRadioButtons, text="【 磁条抗阻设置 】", font=('微软雅黑', 10, 'bold'), fg='#333').pack(side=TOP, pady=3)    
        Radiobutton(coercivityRadioButtons, text="高抗 Hi-Co (常见超市卡)", variable=self.__coercivityRadioBtnValue, value="hi", command=self.coercivity_change).pack(side=TOP, anchor='w')
        Radiobutton(coercivityRadioButtons, text="低抗 Low-Co", variable=self.__coercivityRadioBtnValue, value="low", command=self.coercivity_change).pack(side=TOP, anchor='w')
        
        # 指示灯控制按钮组
        ledButtons = Frame(buttons, padx=10, pady=5)
        ledButtons.pack(side=TOP, padx=10, fill=X)
        Label(ledButtons, text="【 指示灯控制 】", font=('微软雅黑', 10, 'bold'), fg='#333').pack(side=TOP, pady=3)    
        
        led_grid = Frame(ledButtons)
        led_grid.pack(side=TOP)
        Button(led_grid, text="全开", width=6, command=lambda: self.led_change("on")).grid(row=0, column=0, padx=2, pady=2)
        Button(led_grid, text="全关", width=6, command=lambda: self.led_change("off")).grid(row=0, column=1, padx=2, pady=2)
        Button(led_grid, text="绿灯", width=6, command=lambda: self.led_change("green")).grid(row=1, column=0, padx=2, pady=2)
        Button(led_grid, text="黄灯", width=6, command=lambda: self.led_change("yellow")).grid(row=1, column=1, padx=2, pady=2)
        Button(led_grid, text="红灯", width=6, command=lambda: self.led_change("red")).grid(row=2, column=0, columnspan=2, padx=2, pady=2, sticky='ew')
        
        # 硬件自检与测试
        testButtons = Frame(buttons, padx=10, pady=5)
        testButtons.pack(side=TOP, padx=10, fill=X)
        Label(testButtons, text="【 硬件测试 】", font=('微软雅黑', 10, 'bold'), fg='#333').pack(side=TOP, pady=3)    
        Button(testButtons, text="通信测试", command=self.communication_test).pack(side=TOP, fill=X, pady=2)
        Button(testButtons, text="刷卡传感器测试", command=self.sensor_test).pack(side=TOP, fill=X, pady=2)
        Button(testButtons, text="RAM 内存测试", command=self.ram_test).pack(side=TOP, fill=X, pady=2)

    def connect_to_msr605(self):        
        if (self.__connected == True or self.__msr != None):
            self.close_connection()
        
        try:
            self.__msr = cardReader.CardReader()
        
        except cardReaderExceptions.MSR605ConnectError as e:
            self.__connected = False
            self.__connectedLabelIndicator.config(text="● 设备未连接", fg='red')
            showerror("连接失败", f"未能检测到读写器，请确认：\n1. USB 数据线已插紧或蓝牙已配对；\n2. 机器已开机（指示灯正常）；\n3. 端口未被其他软件占用。\n\n详情: {e}")
            print(e)
        
        except cardReaderExceptions.CommunicationTestError as e:
            self.__connected = False
            self.__connectedLabelIndicator.config(text="● 设备未连接", fg='red')
            showerror("通信异常", f"已检测到端口，但设备通信握手失败: {e}")            
            print(e)
        
        else:
            self.__connected = True
            self.__connectedLabelIndicator.config(text="● 设备已连接就绪", fg='#137333')
            showinfo('连接成功', '读写器已成功连接，可以开始读卡或写卡！')
    
    def close_connection(self):
        if (self.__connected == True or self.__msr != None):
            self.__msr.close_serial_connection()
            self.__connected = False
            self.__connectedLabelIndicator.config(text="● 设备未连接", fg='red')
            self.__msr = None
        else:
            showinfo('提示', '读写器当前未连接')
    
    def exception_error_reset(self, title, text):
        showerror(title, f"{text}\n\n正在为您自动复位设备，请重试。")
        self.reset()
        
    def coercivity_change(self):
        if (self.__connected == False or self.__msr == None):
            showerror("未连接", "请先连接读写器！")
            return None
        
        rdbSelection = self.__coercivityRadioBtnValue.get()        
        
        try:
            if (rdbSelection == 'hi'):            
                self.__msr.set_hi_co()
            elif (rdbSelection == 'low'):
                self.__msr.set_low_co()
                
        except cardReaderExceptions.SetCoercivityError as e:
            self.exception_error_reset("抗阻设置失败", e)
            print(e)            
        else:
            try:
                coercivity = self.__msr.get_hi_or_low_co()
            except cardReaderExceptions.GetCoercivityError as e:
                self.exception_error_reset("读取抗阻状态失败", e)
                print(e)
            else:
                desc = "高抗 (Hi-Co)" if "HI" in str(coercivity).upper() else "低抗 (Low-Co)"
                showinfo("设置完成", f"抗磁性已成功设置为: {desc}")
            
    def read_card(self):
        if (self.__connected == False or self.__msr == None):
            showerror("未连接", "请先点击【连接读写器】按钮连接设备！")
            return None
            
        showinfo("准备刷卡", "请点击【确定】，然后拿起卡片平稳匀速划过卡槽。")
        try:
            self.__tracks = self.__msr.read_card()
        except cardReaderExceptions.CardReadError as e:
            self.exception_error_reset("读卡失败", f"刷卡读取未成功 (可能是刷卡速度不均匀或卡片方向反了): {e}")
            print(e)
            
            if hasattr(e, 'tracks'):
                self.__trackOneEntry.delete(1.0, END)
                self.__trackTwoEntry.delete(1.0, END)
                self.__trackThreeEntry.delete(1.0, END)
                self.__trackOneEntry.insert(END, e.tracks[0])
                self.__trackTwoEntry.insert(END, e.tracks[1])
                self.__trackThreeEntry.insert(END, e.tracks[2])
            return None
    
        except cardReaderExceptions.StatusError as e:
            self.exception_error_reset("读取状态错误", e)
            print(e)
            return None
        
        else:
            self.__trackOneEntry.delete(1.0, END)
            self.__trackTwoEntry.delete(1.0, END)
            self.__trackThreeEntry.delete(1.0, END)
            
            self.__trackOneEntry.insert(END, self.__tracks[0])
            self.__trackTwoEntry.insert(END, self.__tracks[1])
            self.__trackThreeEntry.insert(END, self.__tracks[2])
        
            if (self.__autoSaveDatabase.get() == True):
                if (self.__enableDuplicates.get() == False):
                    cursor.execute("""SELECT * FROM Cards WHERE trackOne=? AND trackTwo=? AND trackThree=?""", (self.__tracks))
                    conn.commit()
                    result = cursor.fetchone()
                    if (result != None):
                        showinfo("提示", "该卡片数据已存在于数据库中（如需重复保存，请在顶部【数据库】菜单勾选【允许保存重复卡片】）")
                    else:
                        cursor.execute("""INSERT INTO Cards(trackOne, trackTwo, trackThree) VALUES(?, ?, ?)""", (self.__tracks))                    
                        conn.commit()                
                else:                
                    cursor.execute("""INSERT INTO Cards(trackOne, trackTwo, trackThree) VALUES(?, ?, ?)""", (self.__tracks))                    
                    conn.commit()
            
            showinfo("读取成功", f"读卡成功！\n会员卡号 (第2磁道): {self.__tracks[1] if self.__tracks[1] else '(无数据)'}")
                
    def write_card(self):
        if (self.__connected == False or self.__msr == None):
            showerror("未连接", "请先连接读写器！")
            return None
        
        t1 = self.__trackOneEntry.get(1.0, END)[:-1].strip()
        t2 = self.__trackTwoEntry.get(1.0, END)[:-1].strip()
        t3 = self.__trackThreeEntry.get(1.0, END)[:-1].strip()

        if not t1 and not t2 and not t3:
            showerror("无数据", "磁道输入框内容为空，请输入要写入的卡号后再写卡！")
            return None

        tracks = [t1, t2, t3]
        showinfo("准备写卡", f"即将写入磁道数据：\n第2磁道(卡号): {t2}\n\n请准备好空白卡，点击【确定】后平稳划过卡槽。")
        
        try:        
            self.__tracks = self.__msr.write_card(tracks, True)
        except cardReaderExceptions.CardWriteError as e:
            self.exception_error_reset("写卡失败", f"写卡过程出错: {e}")
            print(e)
            return None
        except cardReaderExceptions.StatusError as e:
            self.exception_error_reset("状态错误", e)
            print(e)
            return None
        else:
            showinfo("写入成功", f"🎉 会员卡写入成功！\n卡号: {t2}")
        
    def erase_card(self):
        if (self.__connected == False or self.__msr == None):
            showerror("未连接", "请先连接读写器！")
            return None
        
        if not askyesno("确认擦除", "确定要擦除卡片上的所有磁道数据吗？\n擦除后数据将不可恢复！"):
            return

        showinfo("准备擦除", "点击【确定】后，请将需要清空的磁条卡平稳划过卡槽。")
        try:
            self.__msr.erase_card(7) # 擦除全部磁道
        except cardReaderExceptions.EraseCardError as e:
            self.exception_error_reset("擦除失败", e)
            print(e)
            return None
        else:
            showinfo("擦除成功", "卡片磁道数据已成功擦除清空！")
            
    def led_change(self, whichLeds):
        if (self.__connected == False or self.__msr == None):
            showerror("未连接", "请先连接读写器！")
            return None
       
        if (whichLeds == "on"):
            self.__msr.led_on()
        elif (whichLeds == "off"):
            self.__msr.led_off()
        elif (whichLeds == "green"):
            self.__msr.green_led_on()
        elif (whichLeds == "yellow"):
            self.__msr.yellow_led_on()
        elif (whichLeds == "red"):
            self.__msr.red_led_on()
            
    def reset(self):
        if (self.__connected == False or self.__msr == None):
            showerror("未连接", "读写器未连接，无需复位")
            return None
        self.__msr.reset()
        showinfo("复位完成", "读写器已成功复位到初始就绪状态。")
    
    def communication_test(self):
        if (self.__connected == False or self.__msr == None):
            showerror("未连接", "请先连接读写器！")
            return None
        try:
            self.__msr.communication_test()
        except cardReaderExceptions.CommunicationTestError as e:
            self.exception_error_reset("测试失败", f"通信异常: {e}")
            print(e)
            return None
        else:
            showinfo("通信正常", "电脑与读写器通信测试通过！数据链路正常。")
        
    def ram_test(self):
        if (self.__connected == False or self.__msr == None):
            showerror("未连接", "请先连接读写器！")
            return None
        try:
            self.__msr.ram_test()
        except cardReaderExceptions.RamTestError as e:
            self.exception_error_reset("测试失败", f"内存自检异常: {e}")
            print(e)
            return None
        else:
            showinfo("内存正常", "读写器内部 RAM 内存检测通过！")
            
    def sensor_test(self):
        if (self.__connected == False or self.__msr == None):
            showerror("未连接", "请先连接读写器！")
            return None
        showinfo("传感器测试", "点击【确定】后，请划过任意一张卡片测试传感器感应。")
        try:
            self.__msr.sensor_test()
        except cardReaderExceptions.SensorTestError as e:
            self.exception_error_reset("测试未通过", f"传感器未感应到刷卡: {e}")
            print(e)
            return None
        else:
            showinfo("传感器正常", "读写器刷卡传感器工作正常！")

    def view_database(self):
        dbView = tk.Toplevel(self)
        dbView.title("已保存的卡片数据库")
        dbView.minsize(700, 450)
        
        dbTree = ttk.Treeview(dbView)
        dbTree.pack(side=TOP, fill=BOTH, expand=True, padx=10, pady=10)
        
        dbTree['columns'] = ('Track 1', 'Track 2', 'Track 3')
        
        dbTree.column('#0', width=80)
        dbTree.heading('#0', text='序号')
        
        dbTree.column('Track 1', width=180)
        dbTree.heading('Track 1', text='第 1 磁道 (Track 1)')
        
        dbTree.column('Track 2', width=180)
        dbTree.heading('Track 2', text='第 2 磁道 (会员卡号)')
        
        dbTree.column('Track 3', width=180)
        dbTree.heading('Track 3', text='第 3 磁道 (Track 3)')
        
        cursor.execute("""SELECT * FROM Cards""")
        conn.commit()
        tracks = cursor.fetchall()
        
        i = 1
        for track in tracks:            
            dbTree.insert("", END, text=f"卡片 {i}", values=(track[0], track[1], track[2]))
            i += 1

    def on_exit(self):        
        conn.close()
        if (self.__connected == True or self.__msr != None):
            self.close_connection()
        root.destroy()
        

root = tk.Tk()
root.title("超市会员卡 磁条卡读写管理系统 (DEFTUN / MSR605)")
root.minsize(750, 560)
gui = GUI(root)

conn = sqlite3.connect("cardDatabase.db") 
cursor = conn.cursor()
cursor.execute("""CREATE TABLE if not exists Cards
                  (trackOne text, trackTwo text, trackThree text) 
               """)
conn.commit()

root.pack_propagate(0)
root.protocol("WM_DELETE_WINDOW", lambda: gui.on_exit())
root.mainloop()