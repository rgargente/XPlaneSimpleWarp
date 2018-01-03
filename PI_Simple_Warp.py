# Copyright (c) 2015, Lionel Zamouth - lionel@zamouth.be
# All rights reserved.
#
# License and some functions copied from various Massimo Ferrarini's scripts
# Thanks to Sandy Barbour for the Python plugin
#
# BSD-style license:
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the PI_Simple_Warp nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY Lionel Zamouth "AS IS" AND ANY
# EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL Lionel Zamouth BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# PI_Simple_Warp.py
# Teleport aircraft toward waypoint
#
#
VERSION = "1.1"

from XPLMDefs import *
from XPLMDisplay import *
from XPLMGraphics import *
from XPLMMenus import *
from XPLMNavigation import *
from XPWidgetDefs import *
from XPWidgets import *
from XPStandardWidgets import *
from XPLMDataAccess import *
from SandyBarbourUtilities import *
from PythonScriptMessaging import *
from XPLMProcessing import *
from XPLMUtilities import *

from numbers import Number
from datetime import datetime
from collections import namedtuple
from timeit import default_timer as timer
import os, platform, string, ConfigParser, math

#import pyperclip

FILE_INI = "Simple_Warp.ini"
FILE_LOG = "Simple_Warp.txt"
FILE_PRE = "Simple_Warp.prf"
FILE_INF = "cycle_info.txt"
FILE_AWY = "earth_awy.dat"
FILE_FIX = "earth_fix.dat"
FILE_NAV = "earth_nav.dat"

SHOW_MENU = 1
PREF_MENU = 2

MARGIN_W = 30
MARGIN_H = 30
WINDOW_W = 350
WINDOW_H = 50

NavType = {
    xplm_Nav_Unknown:       "UKN",
    xplm_Nav_Airport:       "APT",
    xplm_Nav_NDB:           "NDB",
    xplm_Nav_VOR:           "VOR",
    xplm_Nav_ILS:           "ILS",
    xplm_Nav_Localizer:     "LOC",
    xplm_Nav_GlideSlope:    "GS",
    xplm_Nav_OuterMarker:   "OM",
    xplm_Nav_MiddleMarker:  "MM",
    xplm_Nav_InnerMarker:   "IM",
    xplm_Nav_Fix:           "FIX",
    xplm_Nav_DME:           "DME",
    xplm_Nav_LatLon:        "L/L"}

NavAid  = namedtuple('NavAid' , ['typ', 'lat', 'lon','name','height','freq'])
Segment = namedtuple('Segment',['Start','End'])
Coords  = namedtuple('Coords' ,['lat','lon'])

class PythonInterface:
    def XPluginStart(self):
        self.Name = "Simple Warp v" + VERSION
        self.Sig = "lzh.python.Simple_Warp"
        self.Desc = "Teleport aircraft close to next waypoint"
        self.NavInfo = ""
        self.SWWindowCreated = False
        self.SearchFix = ""
        self.destLat  = 0.0
        self.destLon  = 0.0
        self.destName = ""
        self.findAid = 0
        self.foundAid = False

        # Load preferences
        self.LoadPrefs()
        # Debug
        self.DebugInit()
        self.DebugPrint("Debug to console: {}, debug to file: {}".format(self.DebugToConsole,self.DebugToFile))

        # Menus
        self.SWMenuHandlerCB = self.SWMenuHandler
        self.mPluginItem = XPLMAppendMenuItem(XPLMFindPluginsMenu(), "Python - Simple Warp", 0, 1)
        self.mMain = XPLMCreateMenu(self, "Simple Warp", XPLMFindPluginsMenu(), self.mPluginItem, self.SWMenuHandlerCB, 0)
        self.mShowItem = XPLMAppendMenuItem(self.mMain, "Show Simple Warp panel" , SHOW_MENU, 1)

        # Custom Command
        self.SWToggle = XPLMCreateCommand("lzh/python/Simple_Warp_toggle", "Toggle Simple Warp window")
        self.SWToggleHandlerCB = self.SWToggleHandler
        XPLMRegisterCommandHandler(self, self.SWToggle, self.SWToggleHandlerCB, 1, 0)

        # Done with start, return identity
        return self.Name, self.Sig, self.Desc

    def XPluginStop(self):
        if self.SWWindowCreated:
            XPDestroyWidget(self, self.SWWindow, 1)
            self.SWWindowCreated = False
        if self.DebugFile != None:
            self.DebugFile.close()
        XPLMDestroyMenu(self,self.mMain)
        XPLMUnregisterCommandHandler(self, self.SWToggle, self.SWToggleHandlerCB, 0, 0)
        pass

    def XPluginEnable(self):
        return 1

    def XPluginDisable(self):
        pass

    def XPluginReceiveMessage(self, inFromWho, inMessage, inParam):
        pass

    def SWToggleHandler(self, inCommand, inPhase, inRefcon):
        # execute the command only on press
        if inPhase == 0:
            if not self.SWWindowCreated:
                self.CreateSWWindow()
                self.SWWindowCreated = True
            else:
                if not XPIsWidgetVisible(self.SWWindow):
                    XPShowWidget(self.SWWindow)
                else:
                    XPHideWidget(self.SWWindow)
        return 0

    def SWMenuHandler(self, inMenuRef, inItemRef):
        if inItemRef == SHOW_MENU:
            if not self.SWWindowCreated:
                self.CreateSWWindow()
                self.SWWindowCreated = True
            else:
                if not XPIsWidgetVisible(self.SWWindow):
                    XPShowWidget(self.SWWindow)
        else:
            self.DebugPrint( "Unknown menu option " + str(inItemRef))

    def SWWindowHandler(self, inMessage, inWidget, inParam1, inParam2):
        # Close button will only hide window
        if inMessage == xpMessage_CloseButtonPushed:
            if self.SWWindowCreated:
                XPHideWidget(self.SWWindow)
            return 1

        # Handle all button pushes
        if inMessage == xpMsg_PushButtonPressed:
            if inParam1 == self.BtnWarp:
                self.WarpAircraft()
                return 1
            if inParam1 == self.BtnWarn:
                self.CmdClearWarning()
                return 1
            if inParam1 == self.BtnFind:
                self.CmdFindAid()
                return 1
            if inParam1 == self.BtnNext:
                self.CmdNextAid()
                return 1
        elif inMessage == xpMsg_ButtonStateChanged:
            if inParam1 == self.WrpUse:
                self.warp_Use = bool(XPGetWidgetProperty(self.WrpUse, xpProperty_ButtonState, None))
                return 1
            if inParam1 == self.Pref1Btn:
                self.Translucent = bool(XPGetWidgetProperty(self.Pref1Btn, xpProperty_ButtonState, None))
                self.SetTranslucency()
                self.SavePrefs()
                return 1
        return 0

    def CreateSWWindow(self):
        if self.SWWindowCreated:
            XPDestroyWidget(self, self.SWWindow, 1)
        outW, outH = [], []
        XPLMGetScreenSize(outW, outH)
        x, y, w, h = int(outW[0]) - WINDOW_W - MARGIN_W, int(outH[0]) - MARGIN_H, WINDOW_W, WINDOW_H

        x2 = x + w
        y2 = y - 135
        hhh, spx, spy, spt = 20, 15, 20, 5
        ww1, ww2, ww3, ww4, ww5, ww6 , ww7= 10, 85, 30, 40, 60, 65, 30
        xx1 = x+5
        xx2 = xx1+ww1+spx
        xx3 = xx2+ww2+spx
        xx4 = xx3+ww3+spx
        xx5 = xx4+ww4+spx
        xx6 = xx5+ww5+spx
        xx7 = xx6+ww6+spx
        yyi = y - 18
        Buffer = "Simple Warp rev. " + VERSION

        # Create the Main Widget window
        self.SWWindow     = XPCreateWidget(x  , y  , x2  , y2  , 1, Buffer, 1,  0, xpWidgetClass_MainWindow)
        XPSetWidgetProperty(self.SWWindow, xpProperty_MainWindowHasCloseBoxes, 1)
        self.SWWindowTabs = XPCreateWidget(x+3, yyi, x2-3, y2+3, 1, ""    , 0, self.SWWindow, xpWidgetClass_SubWindow)
        yyi -= 4

        www = int( (w - 17 - 4*spt) / 5)
        # Message textbox and clear button
        self.WarnMsg = XPCreateWidget(xx1  , yyi, x2-60, yyi-hhh, 1, "Welcome to Simple Warp", 0, self.SWWindow, xpWidgetClass_Caption)
        self.BtnWarn = XPCreateWidget(x2-50, yyi, x2-5 , yyi-hhh, 1, "Clear"    , 0, self.SWWindow, xpWidgetClass_Button)
        XPSetWidgetProperty(self.BtnWarn, xpProperty_ButtonType, xpPushButton)
        yyi -= spy

        yyi -= int(spy/2)
        saveyyi = yyi

        self.WrpFix  = XPCreateWidget(xx1    , yyi, xx1+40 , yyi-hhh, 1, ""             , 0, self.SWWindow, xpWidgetClass_TextField)
        self.BtnFind = XPCreateWidget(xx1+45 , yyi, xx1+85 , yyi-hhh, 1, "Find"         , 0, self.SWWindow, xpWidgetClass_Button)
        self.BtnNext = XPCreateWidget(xx1+90 , yyi, xx1+130, yyi-hhh, 1, "Next"         , 0, self.SWWindow, xpWidgetClass_Button)
        self.WrpLb0  = XPCreateWidget(xx1+135, yyi, xx1+250, yyi-hhh, 1, "Navaid ID (empty for FMS)", 0, self.SWWindow, xpWidgetClass_Caption)
        self.BtnWarp = XPCreateWidget(x2-50  , yyi, x2-5   , yyi-hhh, 1, "!Warp!"       , 0, self.SWWindow, xpWidgetClass_Button)
        XPSetWidgetProperty(self.BtnFind, xpProperty_ButtonType, xpPushButton)
        XPSetWidgetProperty(self.BtnNext, xpProperty_ButtonType, xpPushButton)
        XPSetWidgetProperty(self.BtnWarp, xpProperty_ButtonType, xpPushButton)
        yyi -= spy

        self.WrpDst = XPCreateWidget(xx1   , yyi, xx1+40 , yyi-hhh, 1, ""                                            , 0, self.SWWindow, xpWidgetClass_TextField)
        self.WrpLb1 = XPCreateWidget(xx1+45, yyi, xx1+250, yyi-hhh, 1, "Warp as close as ... (min=1nm, default=10nm)", 0, self.SWWindow, xpWidgetClass_Caption)
        XPSetWidgetDescriptor(self.WrpDst, str(self.warp_Dst))
        yyi -= spy

        self.WrpMax = XPCreateWidget(xx1   , yyi, xx1+40 , yyi-hhh, 1, ""                                            , 0, self.SWWindow, xpWidgetClass_TextField)
        self.WrpLb3 = XPCreateWidget(xx1+45, yyi, xx1+250, yyi-hhh, 1, "Maximum Warp distance (default 100nm)"       , 0, self.SWWindow, xpWidgetClass_Caption)
        XPSetWidgetDescriptor(self.WrpMax, str(self.warp_Max))
        yyi -= spy

        self.WrpUse = XPCreateWidget(xx1+30, yyi, xx1+40 , yyi-hhh, 1, ""                 , 0, self.SWWindow, xpWidgetClass_Button)
        self.WrpLb6 = XPCreateWidget(xx1+45, yyi, xx1+250, yyi-hhh, 1, "Use fuel during warp", 0, self.SWWindow, xpWidgetClass_Caption)
        XPSetWidgetProperty(self.WrpUse, xpProperty_ButtonType    , xpRadioButton)
        XPSetWidgetProperty(self.WrpUse, xpProperty_ButtonBehavior, xpButtonBehaviorCheckBox)
        XPSetWidgetProperty(self.WrpUse, xpProperty_ButtonState   , self.warp_Use)
        XPSetWidgetProperty(self.WrpUse, xpProperty_Enabled, 1)
        #yyi -= spy

        self.Pref1Btn = XPCreateWidget(xx1+200, yyi, xx1+210, yyi-hhh, 1, ""                  , 0, self.SWWindow, xpWidgetClass_Button)
        self.Pref1Lbl = XPCreateWidget(xx1+215, yyi, xx1+340, yyi-hhh, 1, "Translucent window", 0, self.SWWindow, xpWidgetClass_Caption)
        XPSetWidgetProperty(self.Pref1Btn, xpProperty_ButtonType    , xpRadioButton)
        XPSetWidgetProperty(self.Pref1Btn, xpProperty_ButtonBehavior, xpButtonBehaviorCheckBox)
        XPSetWidgetProperty(self.Pref1Btn, xpProperty_ButtonState   , self.Translucent)
        XPSetWidgetProperty(self.Pref1Btn, xpProperty_Enabled, 1)
        yyi -= spy

        # Register the widget handler
        self.SWWindowHandlerCB = self.SWWindowHandler
        XPAddWidgetCallback(self, self.SWWindow, self.SWWindowHandlerCB)
        self.SetTranslucency()

    def SetTranslucency(self):
        if self.Translucent:
            XPHideWidget(self.SWWindowTabs)
            XPSetWidgetProperty(self.SWWindow, xpProperty_MainWindowType, xpMainWindowStyle_Translucent)
        else:
            XPShowWidget(self.SWWindowTabs)
            XPSetWidgetProperty(self.SWWindow, xpProperty_MainWindowType, xpMainWindowStyle_MainWindow)

        XPSetWidgetProperty(self.WarnMsg, xpProperty_CaptionLit, self.Translucent)

        XPSetWidgetProperty(self.Pref1Lbl, xpProperty_CaptionLit, self.Translucent)
        #XPSetWidgetProperty(self.Pref2Lbl, xpProperty_CaptionLit, self.Translucent)
        #XPSetWidgetProperty(self.Pref3Lbl, xpProperty_CaptionLit, self.Translucent)

        XPSetWidgetProperty(self.WrpLb0, xpProperty_CaptionLit, self.Translucent)
        XPSetWidgetProperty(self.WrpLb1, xpProperty_CaptionLit, self.Translucent)
        #XPSetWidgetProperty(self.WrpLb2, xpProperty_CaptionLit, self.Translucent)
        XPSetWidgetProperty(self.WrpLb3, xpProperty_CaptionLit, self.Translucent)
        #XPSetWidgetProperty(self.WrpLb4, xpProperty_CaptionLit, self.Translucent)
        #XPSetWidgetProperty(self.WrpLb5, xpProperty_CaptionLit, self.Translucent)
        XPSetWidgetProperty(self.WrpLb6, xpProperty_CaptionLit, self.Translucent)

    def CmdClearWarning(self):
        XPSetWidgetDescriptor(self.WarnMsg, " ")
        XPSetWidgetProperty(self.BtnWarn, xpProperty_Enabled, 0)
        XPSetWidgetDescriptor(self.WrpFix, "")
        self.findAid = 0
        self.foundAid = False

    def CmdDisplayWarning(self,text):
        XPSetWidgetDescriptor(self.WarnMsg, text)
        XPSetWidgetProperty(self.BtnWarn, xpProperty_Enabled, 1)

    def SavePrefs(self):
        baseDir = os.path.join(XPLMGetSystemPath(), "Output", "preferences")
        filePre = os.path.join(baseDir, FILE_PRE)
        with open(filePre,"w") as fh:
            fh.write("# Simple Warp preferences" + os.linesep)
            fh.write("Translucent {}".format(self.Translucent) + os.linesep)
            fh.write("Warp_Dst {}".format(self.warp_Dst) + os.linesep)
            fh.write("Warp_Max {}".format(self.warp_Max) + os.linesep)
            fh.write("Warp_Use {}".format(self.warp_Use) + os.linesep)

    def LoadPrefs(self):
        self.Translucent    = True
        self.DebugToConsole = True
        self.DebugToFile    = True
        self.DebugFile      = None
        self.warp_Dst = 10
        #self.warp_Min = 20
        self.warp_Max = 100
        #self.warp_Alt = 200
        #self.warp_Spd = 200
        self.warp_Use = False

        baseDir = os.path.join(XPLMGetSystemPath(), "Output", "preferences")
        filePre = os.path.join(baseDir, FILE_PRE)
        try:
            with open(filePre,"rU") as fh:
                lines = fh.read().splitlines()
                self.DebugPrint( "Reading preferences from Output/preferences/{}".format(FILE_PRE))
                for line in lines:
                    fields = line.upper().strip().split()
                    if len(fields) != 2: continue
                    if fields[0] == "TRANSLUCENT"   and str(fields[1]) in ['1','YES','TRUE']:
                        self.Translucent = True
                    #if fields[0] == "DEBUGTOCONSOLE" and str(fields[1]) in ['1','YES','TRUE']:
                    #    self.DebugToConsole = True
                    #if fields[0] == "DEBUGTOFILE"    and str(fields[1]) in ['1','YES','TRUE']:
                    #    self.DebugToFile = True
                    if fields[0] == "WARP_USE"    and str(fields[1]) in ['1','YES','TRUE']:
                        self.warp_Use = True
                    if fields[0] == "WARP_DST":
                        try:
                            self.warp_Dst = int(fields[1])
                        except:
                            pass
                    #if fields[0] == "WARP_MIN":
                    #    try:
                    #        self.warp_Min = int(fields[1])
                    #    except:
                    #        pass
                    if fields[0] == "WARP_MAX":
                        try:
                            self.warp_Max = int(fields[1])
                        except:
                            pass
                    #if fields[0] == "WARP_ALT":
                    #    try:
                    #        self.warp_Alt = int(fields[1])
                    #    except:
                    #        pass
                    #if fields[0] == "WARP_SPD":
                    #    try:
                    #        self.warp_Spd = int(fields[1])
                    #    except:
                    #        pass

        except:
            self.DebugPrint("Caught top level exception in LoadPrefs")
            pass
        self.SavePrefs()

    def DebugPrint(self, Msg):
        message = str(datetime.now()) + " " + self.Name + ": " + Msg
        if self.DebugToConsole:
            #SandyBarbourPrint(Msg)
            print message
        if self.DebugToFile and self.DebugFile:
            self.DebugFile.write(message + os.linesep)
            self.DebugFile.flush()

    def DebugInit(self):
        self.DebugFile = None
        if self.DebugToFile:
            baseDir = os.path.join(XPLMGetSystemPath(), "Resources", "plugins", "PythonScripts")
            fileLog = os.path.join(baseDir, FILE_LOG)
            try:
                self.DebugFile = open(fileLog, "a")
            except:
                self.DebugToFile = False
                self.DebugToConsole = True
                self.DebugPrint("Failed to open debug log file, forcing debug to console.")
                self.DebugPrint("-> {}".format(fileLog))

    def GetMyCoords(self):
        myLatDR = XPLMFindDataRef("sim/flightmodel/position/latitude")
        myLonDR = XPLMFindDataRef("sim/flightmodel/position/longitude")
        return XPLMGetDataf(myLatDR), XPLMGetDataf(myLonDR)

    def NavDistance(self, degLat1, degLon1, degLat2, degLon2):
        #radius = 6371 # km
        radius = 3440.07 # nm
        radLat1  = math.radians(degLat1)
        radLat2  = math.radians(degLat2)
        deltaLat = math.radians(degLat2-degLat1)
        deltaLon = math.radians(degLon2-degLon1)

        sLat = math.sin(deltaLat/2)
        sLon = math.sin(deltaLon/2)
        a = sLat*sLat + math.cos(radLat1) * math.cos(radLat2) * sLon*sLon
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return radius * c

    def GeoDistance(self, coords1, coords2):
        degLat1, degLon1 = coords1
        degLat2, degLon2 = coords2
        #radius = 6371 # km
        radius = 3440.07 # nm
        radLat1  = math.radians(degLat1)
        radLat2  = math.radians(degLat2)
        deltaLat = math.radians(degLat2-degLat1)
        deltaLon = math.radians(degLon2-degLon1)

        sLat = math.sin(deltaLat/2)
        sLon = math.sin(deltaLon/2)
        a = sLat*sLat + math.cos(radLat1) * math.cos(radLat2) * sLon*sLon
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return radius * c

    def WarpAircraft(self):

        if self.destLat == 0.0 and self.destLon == 0.0:
            self.CmdDisplayWarning("Nowhere to warp to")
            return

        drx = XPLMFindDataRef("sim/flightmodel/position/local_x")
        dry = XPLMFindDataRef("sim/flightmodel/position/local_y")
        drz = XPLMFindDataRef("sim/flightmodel/position/local_z")
        dre = XPLMFindDataRef("sim/flightmodel/position/elevation")
        drp = XPLMFindDataRef("sim/cockpit/autopilot/altitude")
        drg = XPLMFindDataRef("sim/cockpit2/gauges/indicators/altitude_ft_pilot")
        dri = XPLMFindDataRef("sim/flightmodel/position/indicated_airspeed")
        drs = XPLMFindDataRef("sim/flightmodel/position/groundspeed")

        local_x   = XPLMGetDatad(drx)
        local_y   = XPLMGetDatad(dry)
        local_z   = XPLMGetDatad(drz)
        elevation = XPLMGetDatad(dre)
        autopilot = XPLMGetDataf(drp)
        gauge_alt = XPLMGetDataf(drg)
        IAS       = XPLMGetDataf(dri)
        grounds   = XPLMGetDataf(drs)

        buff = []
        XPGetWidgetDescriptor(self.WrpDst, buff, 256)
        try:
            self.warp_Dst = int(buff[0])
        except:
            self.CmdDisplayWarning("{} is not a valid value".format(buff[0]))
            return

        buff = []
        XPGetWidgetDescriptor(self.WrpMax, buff, 256)
        try:
            self.warp_Max = int(buff[0])
        except:
            self.CmdDisplayWarning("{} is not a valid value".format(buff[0]))
            return

        my_Lat, my_Lon = self.GetMyCoords()

        self.DebugPrint("Preparing warp")
        wpt_x, wpt_y, wpt_z = XPLMWorldToLocal(self.destLat, self.destLon, local_y)
        #self.DebugPrint("WPT: {} {} {}".format(wpt_x, wpt_y, wpt_z))
        delta_x = wpt_x - local_x
        delta_y = wpt_y - local_y
        delta_z = wpt_z - local_z

        # Too close to warp
        distance = math.sqrt(delta_x*delta_x + delta_y*delta_y + delta_z*delta_z) / 1852.0
        #if distance < self.warp_Min:
        #    self.CmdDisplayWarning("Too close to next waypoint ({}nm)".format(int(distance)))
        #    self.DebugPrint("Too close to next waypoint ({}nm)".format(int(distance)))
        #    return

        # Warp 5nm from destination or 100nm max (params now)
        travel = min(self.warp_Max, distance - self.warp_Dst)
        warp_factor = travel / distance
        self.DebugPrint("Distance {}nm, warp factor {}".format(int(travel*100)/100.0, warp_factor))
        warp_x = warp_factor * delta_x
        warp_y = warp_factor * delta_y
        warp_z = warp_factor * delta_z

        # Now doing what is recommened not to do, trying to be at same altitude...
        outLat, outLon, outAlt = XPLMLocalToWorld(local_x + warp_x, local_y + warp_y, local_z + warp_z)
        #wpt_x, wpt_y, wpt_z = XPLMWorldToLocal(outLat, outLon, local_y)
        wpt_x, wpt_y, wpt_z = XPLMWorldToLocal(outLat, outLon, elevation)

        # Let's burn some fuel
        burnt = 0
        if self.warp_Use:
            travel_meters = travel * 1852
            time_saved = travel_meters / grounds

            dr_num_tanks   = XPLMFindDataRef("sim/aircraft/overflow/acf_num_tanks")
            dr_num_engines = XPLMFindDataRef("sim/aircraft/engine/acf_num_engines")
            num_tanks   = XPLMGetDatai(dr_num_tanks)
            num_engines = XPLMGetDatai(dr_num_engines)

            dr_tanks = XPLMFindDataRef("sim/flightmodel/weight/m_fuel")
            tanks = []
            XPLMGetDatavf(dr_tanks, tanks, 0, num_tanks)
            total_fuel = 0
            for i in range(num_tanks):
                total_fuel += tanks[i]
                self.DebugPrint("Tank #{}: {} kg".format(i, tanks[i]))

            dr_flows = XPLMFindDataRef("sim/cockpit2/engine/indicators/fuel_flow_kg_sec")
            flows = []
            XPLMGetDatavf(dr_flows, flows, 0, num_engines)
            total_flow = 0
            for i in range(num_engines):
                total_flow += flows[i]
                self.DebugPrint("Engine #{}: {} kg/sec".format(i, flows[i]))

            self.DebugPrint("Total fuel: {:.2f}kg Total fuel flow: {:.2f}".format(total_fuel, total_flow))
            usage = time_saved * total_flow
            burnt = usage
            self.DebugPrint("Fuel to burn for {:.2f}nm in {:.2f}sec : {:.2f}kg".format(travel, time_saved, usage))

            self.DebugPrint("Tanks before: {}".format(tanks))

            if usage > total_fuel:
                self.CmdDisplayWarning("Not enough fuel, you're in trouble...")
                return
            # take from central tank if there's such
            center = 0
            if num_tanks % 2:
                center = (num_tanks - 1) / 2
                if tanks[center] > usage:
                    tanks[center] -= usage
                    usage = 0.0
                else:
                    usage -= tanks[center]
                    tanks[center] = 0.0
                tl, tr = center - 1, center + 1
            else:
                tr = num_tanks / 2
                tl = tr -1
            # then start emptying from center to outside, 2 by 2
            while usage > 0.0 and tl >= 0:
                # not enough in those tanks, empty them
                if (tanks[tl] + tanks[tr]) < usage:
                    usage -= (tanks[tl] + tanks[tr])
                    tanks[tl], tanks[tr] = 0.0, 0.0
                    tl -= 1
                    tr += 1
                    continue
                # enough excess in left tank, take all from there
                if tanks[tl] - tanks[tr] > usage:
                    tanks[tl] -= usage
                    break
                # enough excess in right tank, take all from there
                if tanks[tr] - tanks[tl] > usage:
                    tanks[tr] -= usage
                    break
                # enough in tanks combined, even the tanks
                delta = tanks[tl] - tanks[tr]
                tanks[tl] -= (usage + delta) / 2
                tanks[tr] -= (usage - delta) / 2
                break
            # Update tanks with new values
            self.DebugPrint("Tanks after: {}".format(tanks))
            XPLMSetDatavf(dr_tanks, tanks, 0, num_tanks)

        # Do it!
        XPLMSetDatad(drx, wpt_x)
        XPLMSetDatad(dry, wpt_y)
        XPLMSetDatad(drz, wpt_z)

        self.CmdDisplayWarning("Warped {}nm using {:.0f}kg".format(int(travel*100)/100.0, burnt))
        self.SavePrefs()

    def ResetWarpDefaults(self):
        self.warp_Dst = 10
        self.warp_Min = 20
        self.warp_Max = 100
        self.warp_Alt = 200
        self.warp_Spd = 200
        self.warp_Use = False
        XPSetWidgetDescriptor(self.WrpDst, str(self.warp_Dst))
        XPSetWidgetDescriptor(self.WrpMin, str(self.warp_Min))
        XPSetWidgetDescriptor(self.WrpMax, str(self.warp_Max))
        XPSetWidgetDescriptor(self.WrpAlt, str(self.warp_Alt))
        XPSetWidgetDescriptor(self.WrpSpd, str(self.warp_Spd))
        XPSetWidgetProperty(self.WrpUse, xpProperty_ButtonState, self.warp_Use)
        self.SavePrefs()

    def CmdFindAid(self):
        my_Lat, my_Lon = self.GetMyCoords()
        self.foundAid = False

        buff = []
        XPGetWidgetDescriptor(self.WrpFix, buff, 256)
        self.SearchFix = buff[0].upper()

        if self.SearchFix == "":
            num_FMS = XPLMCountFMSEntries()
            self.DebugPrint("XPLMCountFMSEntries() : {}".format(num_FMS))
            dest_FMS = XPLMGetDestinationFMSEntry()
            self.DebugPrint("XPLMGetDestinationFMSEntry() : {}".format(dest_FMS))
            disp_FMS = XPLMGetDisplayedFMSEntry()
            self.DebugPrint("XPLMGetDisplayedFMSEntry() : {}".format(disp_FMS))
            if num_FMS < 1:
                self.CmdDisplayWarning("You're not heading to a FMS waypoint")
                return

            outType, outID, outLat, outLon = [], [], [], []
            XPLMGetFMSEntryInfo(dest_FMS, outType, outID, None, None, outLat, outLon)
            dest_Type = NavType[int(outType[0])]
            self.SearchFix = outID[0]
            self.destLat  = float(outLat[0])
            self.destLon  = float(outLon[0])
            self.destName = outID[0]
            dist = self.NavDistance(my_Lat, my_Lon, self.destLat, self.destLon)
            if self.destLat == 0.0 and self.destLon == 0.0:
                self.CmdDisplayWarning("You're not heading to a FMS waypoint")
                return
            self.CmdDisplayWarning("FMS[{}] is {} [{}] at {:.1f} nm".format(dest_FMS, outID[0], dest_Type, dist))
            return
        else:
            notdone = True
            myAid = XPLMGetFirstNavAid()
            while notdone:
                outType, outID, outLat, outLon, outName = [], [], [], [], []
                XPLMGetNavAidInfo(myAid, outType, outLat, outLon, None, None, None, outID, outName, None)
                if outID[0] == self.SearchFix:
                    self.destLat  = outLat[0]
                    self.destLon  = outLon[0]
                    self.destName = outName[0]
                    dist = self.NavDistance(my_Lat, my_Lon, self.destLat, self.destLon)
                    self.CmdDisplayWarning("{} [{}] at {:.1f} nm is {}".format(self.SearchFix, NavType[outType[0]], dist, self.destName))
                    self.findAid = myAid
                    self.foundAid = True
                    return
                myAid = XPLMGetNextNavAid(myAid)
                if myAid == XPLM_NAV_NOT_FOUND:
                    notdone = False
        self.destLat = 0.0
        self.destLon = 0.0
        self.CmdDisplayWarning("{} not found".format(self.SearchFix))

    def CmdNextAid(self):
        if not self.foundAid:
            self.CmdDisplayWarning("No previous search")
            return

        my_Lat, my_Lon = self.GetMyCoords()
        notdone = True
        myAid = XPLMGetNextNavAid(self.findAid)
        while notdone:
            outType, outID, outLat, outLon, outName = [], [], [], [], []
            XPLMGetNavAidInfo(myAid, outType, outLat, outLon, None, None, None, outID, outName, None)
            if outID[0] == self.SearchFix:
                self.destLat  = outLat[0]
                self.destLon  = outLon[0]
                self.destName = outName[0]
                dist = self.NavDistance(my_Lat, my_Lon, self.destLat, self.destLon)
                self.CmdDisplayWarning("{} [{}] at {:.1f} nm is {}".format(self.SearchFix, NavType[outType[0]], dist, self.destName))
                self.findAid = myAid
                self.foundAid = True
                return
            myAid = XPLMGetNextNavAid(myAid)
            if myAid == XPLM_NAV_NOT_FOUND:
                notdone = False
        self.findAid = ""
        self.foundAid = False
        self.destLat = 0.0
        self.destLon = 0.0
        self.CmdDisplayWarning("No more entries for {}".format(self.SearchFix))



