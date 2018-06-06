from pcbnew import *

import sys
import os
import os.path
import re
import wx
import wx.lib.filebrowsebutton as FBB

WIDGET_SPACING = 5


def debug_dialog(msg):
    dlg = wx.MessageDialog(None, msg, '', wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


class DnDFilePickerCtrl(FBB.FileBrowseButtonWithHistory, wx.FileDropTarget):
    '''File browser that keeps its history.'''

    def __init__(self, *args, **kwargs):
        FBB.FileBrowseButtonWithHistory.__init__(self, *args, **kwargs)
        wx.FileDropTarget.__init__(self)
        self.SetDropTarget(self)
        self.SetDefaultAction(
            wx.DragCopy)  # Show '+' icon when hovering over this field.

    def GetPath(self, addToHistory=False):
        current_value = self.GetValue()
        if addToHistory:
            self.AddToHistory(current_value)
        return current_value

    def AddToHistory(self, value):
        if value == u'':
            return
        if type(value) in (str, unicode):
            history = self.GetHistory()
            history.insert(0, value)
            history = tuple(set(history))
            self.SetHistory(history, 0)
            self.SetValue(value)
        elif type(value) in (list, tuple):
            for v in value:
                self.AddToHistory(v)

    def SetPath(self, path):
        self.AddToHistory(path)
        self.SetValue(path)

    def OnChanged(self, evt):
        wx.PostEvent(self,
                     wx.PyCommandEvent(wx.EVT_FILEPICKER_CHANGED.typeId,
                                       self.GetId()))

    def OnDropFiles(self, x, y, filenames):
        self.AddToHistory(filenames)
        wx.PostEvent(self,
                     wx.PyCommandEvent(wx.EVT_FILEPICKER_CHANGED.typeId,
                                       self.GetId()))


class LabelledTextCtrl(wx.BoxSizer):
    '''Text-entry box with a label.'''

    def __init__(self, parent, label, value):
        wx.BoxSizer.__init__(self, wx.HORIZONTAL)
        self.lbl = wx.StaticText(parent=parent, label=label)
        self.ctrl = wx.TextCtrl(parent=parent, value=value, style=wx.TE_PROCESS_ENTER)
        self.AddSpacer(WIDGET_SPACING)
        self.Add(self.lbl, 0, wx.ALL | wx.ALIGN_CENTER)
        self.AddSpacer(WIDGET_SPACING)
        self.Add(self.ctrl, 1, wx.ALL | wx.EXPAND)
        self.AddSpacer(WIDGET_SPACING)

class LabelledListBox(wx.BoxSizer):
    '''ListBox with label.'''

    def __init__(self, parent, label, choices):
        wx.BoxSizer.__init__(self, wx.HORIZONTAL)
        self.lbl = wx.StaticText(parent=parent, label=label)
        self.lbx = wx.ListBox(parent=parent, choices=choices, style=wx.LB_EXTENDED|wx.LB_NEEDED_SB|wx.LB_SORT, size=wx.Size(1,50))
        self.AddSpacer(WIDGET_SPACING)
        self.Add(self.lbl, 0, wx.ALL | wx.ALIGN_TOP)
        self.AddSpacer(WIDGET_SPACING)
        self.Add(self.lbx, 1, wx.ALL | wx.EXPAND)
        self.AddSpacer(WIDGET_SPACING)

class Symbol(object):
    '''Object for storing part symbol data.'''
    pass

class Pin(object):
    '''Object for storing pin data.'''
    pass


def get_part_symbols(netlist_file):
    '''Get part symbol information from a netlist file.'''

    # Get the local and global files that contain the symbol tables.
    # Place the global file first so its entries will be overridden by any
    # matching entries in the local file.
    sym_lib_tbls = []
    brd_file = GetBoard().GetFileName()
    brd_dir = os.path.abspath(os.path.dirname(brd_file))
    brd_name = os.path.splitext(os.path.basename(brd_file))[0]
    if sys.platform == 'win32':
        default_home = os.path.expanduser(r'~\AppData\Roaming\kicad')
    else:
        default_home = os.path.expanduser(r'~/.config/kicad')
    dirs = [
        os.environ.get('KICAD_CONFIG_HOME', default_home),
        brd_dir
    ]

    for dir in dirs:
        sym_lib_tbl = os.path.join(dir, 'sym-lib-table')
        if os.path.isfile(sym_lib_tbl):
            sym_lib_tbls.append(sym_lib_tbl)

    # Regular expression for getting the symbol library name and file location.
    sym_tbl_re = '\(lib \(name ([^)]+)\).*\(uri ([^)]+)\)'

    # Process the global and local symbol library tables to create a dict
    # of the symbol library names and their file locations.
    sym_lib_files = {}
    for tbl_file in sym_lib_tbls:
        with open(tbl_file, 'r') as fp:
            for line in fp:
                srch_result = re.search(sym_tbl_re, line)
                if srch_result:
                    lib_name, lib_uri = srch_result.group(1, 2)
                    sym_lib_files[lib_name.lower()] = os.path.expandvars(
                        lib_uri)

    # Add any cache or rescue libraries in the PCB directory.
    for lib_type in ['-cache', '-rescue']:
        lib_name = brd_name + lib_type
        file_name = os.path.join(brd_dir,lib_name+'.lib')
        if os.path.isfile(file_name):
            sym_lib_files[lib_name.lower()] = file_name

    # Regular expressions for getting the part reference and symbol library.
    comp_ref_re = '\(\s*comp\s+\(\s*ref\s+([_A-Za-z][_A-Za-z0-9]*)\)'
    comp_lib_re = '\(\s*libsource\s+\(\s*lib\s+([^)]+)\)\s+\(\s*part\s+([^)]+)\)\)'

    # Scan through the netlist searching for the part references and symbol libraries.
    symbols = {}
    with open(netlist_file, 'r') as fp:
        for line in fp:

            # Search for part reference.
            srch_result = re.search(comp_ref_re, line)
            if srch_result:
                ref = srch_result.group(1)
                symbols[ref] = None
                continue  # Reference found, so continue with next line.

            # Search for symbol library associated with part reference.
            srch_result = re.search(comp_lib_re, line)
            if srch_result:
                symbol = Symbol()
                symbol.lib = srch_result.group(1).lower()
                symbol.part = srch_result.group(2)
                symbols[ref] = symbol
                continue  # Library found, so continue with next line.

    for symbol in symbols.values():
        if symbol is None:
            continue
        try:
            symbol.lib_file = sym_lib_files[symbol.lib]
        except Exception as e:
            symbol.lib_file = 'ERROR'
            debug_dialog('$'+str(e))

    return symbols


def read_part_symbol(ref, symbols):
    try:
        symbol = symbols[ref]
    except Exception:
        raise Exception(ref + ' not a valid part!')
    lib_file = symbol.lib_file
    part = symbol.part

    symbol.pins = {}
    symbol.units = set()
    with open(lib_file, 'r') as fp:
        part_found = False
        for line in fp:
            if part_found:
                if line.startswith('ENDDEF'):
                    break
                if line.startswith('X '):
                    pin_info = line.split()
                    pin = Pin()
                    pin.num = pin_info[2]
                    pin.name = pin_info[1]
                    pin.func = pin_info[11]
                    pin.unit = pin_info[9]
                    symbol.pins[pin.num] = pin
                    symbol.units.add(pin.unit)
                continue
            #part_found = re.search(r'^DEF\s+'+part+r'\s+', line)
            part_found = line.startswith('DEF '+part+' ')


def guess_netlist_file():
    '''Try to find the netlist file for this PCB.'''
    design_name = os.path.splitext(os.path.abspath(
        GetBoard().GetFileName()))[0]
    netlist_file_name = design_name + '.net'
    if os.path.isfile(netlist_file_name):
        return netlist_file_name
    return None


class PadPainterFrame(wx.Frame):
    def __init__(self, title):
        '''Create the GUI for the pad painter.'''

        wx.Frame.__init__(
            self, None, title=title, pos=(150, 150), size=(550, 290))

        # menu_bar = wx.MenuBar()
        # menu = wx.Menu()

        # menu.Append(wx.ID_EXIT, 'E&xit\tAlt-X', 'Exit')
        # self.Bind(wx.EVT_MENU, self.OnTimeToClose, id=wx.ID_EXIT)

        # menu_bar.Append(menu, '&File')
        # self.SetMenuBar(menu_bar)

        # self.CreateStatusBar()

        # Main panel holding all the widgets.
        panel = wx.Panel(self)

        # File browser widget for getting netlist file for this layout.
        netlist_file_wildcard = 'Netlist File|*.net|All Files|*.*'
        self.netlist_file_picker = DnDFilePickerCtrl(
            parent=panel,
            labelText='Netlist File:',
            buttonText='Browse',
            toolTip=
            'Drag-and-drop netlist file associated with this layout or browse for file or enter file name.',
            dialogTitle='Select netlist file associated with this layout',
            initialValue=guess_netlist_file(),
            fileMask=netlist_file_wildcard,
            fileMode=wx.FD_OPEN)
        self.Bind(wx.EVT_FILEPICKER_CHANGED, self.UpdateUnits, self.netlist_file_picker)

        # Widget for specifying which parts to paint. It starts off preloaded
        # with any parts that have already been selected in the PCBNEW layout.
        selected_parts = ','.join([
            p.GetReference() for p in GetBoard().GetModules()
            if p.IsSelected()
        ])
        self.parts = LabelledTextCtrl( parent=panel, label='Parts:', value=selected_parts)
        self.Bind(wx.EVT_TEXT_ENTER, self.UpdateUnits, self.parts.ctrl)

        # Widget for specifying the units in the parts that will be painted.
        self.units = LabelledListBox(parent=panel, label='Units:', choices=[])

        # Widget for specifying the pin numbers in the parts that will be painted.
        self.nums = LabelledTextCtrl(
            parent=panel, label='Pin Numbers:', value='.*')

        # Widget for specifying the pin names in the parts that will be painted.
        self.names = LabelledTextCtrl(
            parent=panel, label='Pin Names:', value='.*')

        # Checkboxes for selecting which types of pins will be painted.
        self.pin_func_btn_lbls = {
            'In': 'I', 
            'Out': 'O', 
            'I/O': 'B', 
            'Tristate': 'T', 
            'Pwr In': 'W',
            'Pwr Out': 'w',
            'Passive': 'P',
            'Unspec.': 'U',
            'OpenColl': 'C',
            'OpenEmit': 'E',
            'NC': 'N',
        }
        self.pin_func_btns = {
            lbl: wx.CheckBox(panel, label=lbl)
            for lbl in self.pin_func_btn_lbls
        }
        for btn_lbl in self.pin_func_btns:
            self.pin_func_btns[btn_lbl].SetLabel(btn_lbl)
        self.all_ckbx = wx.CheckBox(panel, label='All')  # Check all the boxes.
        self.none_ckbx = wx.CheckBox(
            panel, label='None')  # Uncheck all the boxes.
        self.Bind(wx.EVT_CHECKBOX,
                  self.HandlePinFuncBtns)  # Function to handle the checkboxes.

        # Action buttons for painting and clearing the selected pads.
        self.paint_btn = wx.Button(panel, -1, 'Paint')
        self.clear_btn = wx.Button(panel, -1, 'Clear')
        self.done_btn = wx.Button(panel, -1, 'Done')
        self.Bind(wx.EVT_BUTTON, self.OnPaint, self.paint_btn)
        self.Bind(wx.EVT_BUTTON, self.OnClear, self.clear_btn)
        self.Bind(wx.EVT_BUTTON, self.OnDone, self.done_btn)

        # Create a horizontal sizer for holding all the pin-function checkboxes.
        pin_func_sizer = wx.BoxSizer(wx.HORIZONTAL)
        pin_func_sizer.AddSpacer(WIDGET_SPACING)
        pin_func_sizer.Add(
            wx.StaticText(panel, label='Pin Functions:'),
            flag=wx.ALL | wx.ALIGN_CENTER)
        for pin_func_btn_lbl in self.pin_func_btn_lbls:
            pin_func_sizer.AddSpacer(WIDGET_SPACING)
            pin_func_sizer.Add(
                self.pin_func_btns[pin_func_btn_lbl],
                flag=wx.ALL | wx.ALIGN_CENTER)
        pin_func_sizer.AddSpacer(3 * WIDGET_SPACING)
        pin_func_sizer.Add(self.all_ckbx, flag=wx.ALL | wx.ALIGN_CENTER)
        pin_func_sizer.AddSpacer(WIDGET_SPACING)
        pin_func_sizer.Add(self.none_ckbx, flag=wx.ALL | wx.ALIGN_CENTER)

        # Create a horizontal sizer for holding the action buttons.
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddSpacer(WIDGET_SPACING)
        btn_sizer.Add(self.paint_btn, flag=wx.ALL | wx.ALIGN_CENTER)
        btn_sizer.AddSpacer(WIDGET_SPACING)
        btn_sizer.Add(self.clear_btn, flag=wx.ALL | wx.ALIGN_CENTER)
        btn_sizer.AddSpacer(WIDGET_SPACING)
        btn_sizer.Add(self.done_btn, flag=wx.ALL | wx.ALIGN_CENTER)
        btn_sizer.AddSpacer(WIDGET_SPACING)

        # Create a vertical sizer to hold everything in the panel.
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.netlist_file_picker, 0, wx.ALL | wx.EXPAND,
                  WIDGET_SPACING)
        sizer.Add(self.parts, 0, wx.ALL | wx.EXPAND, WIDGET_SPACING)
        sizer.Add(self.units, 0, wx.ALL | wx.EXPAND, WIDGET_SPACING)
        sizer.Add(self.nums, 0, wx.ALL | wx.EXPAND, WIDGET_SPACING)
        sizer.Add(self.names, 0, wx.ALL | wx.EXPAND, WIDGET_SPACING)
        sizer.Add(pin_func_sizer, 0, wx.ALL, WIDGET_SPACING)
        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, WIDGET_SPACING)
        panel.SetSizer(sizer)
        panel.Layout()

        #self.FileBrowserHandler(0)

    def UpdateUnits(self, evt):
        '''Update the list of part units.'''
        self.symbols = get_part_symbols(self.netlist_file_picker.GetPath())
        self.part_refs = [p.strip() for p in self.parts.ctrl.GetValue().split(',')]
        for ref in self.part_refs:
            read_part_symbol(ref, self.symbols)

        units = set()
        for ref in self.part_refs:
            units |= self.symbols[ref].units

        self.units.lbx.Clear()
        self.units.lbx.InsertItems(list(units),0)


    def GetUnits(self):
        lbx = self.units.lbx
        return [lbx.GetString(i) for i in lbx.GetSelections()]


    def OnPaint(self, evt):
        '''Paint the specified pads.'''
        selected_units = self.GetUnits()
        num_re = self.nums.ctrl.GetValue()
        name_re = self.names.ctrl.GetValue()
        for part in GetBoard().GetModules():
            ref = part.GetReference()
            if self.part_refs and (ref not in self.part_refs):
                continue
            try:
                symbol = self.symbols[ref]
            except KeyError:
                continue
            for pad in part.Pads():
                pin = symbol.pins[pad.GetName()]
                if pin.unit in selected_units and re.search(num_re, pin.num) and re.search(name_re, pin.name) and pin.func in self.selected_pin_funcs:
                    pad.SetBrightened()
        Refresh()

    def OnClear(self, evt):
        '''Clear the specified pads.'''
        # self.symbols = get_part_symbols(self.netlist_file_picker.GetPath())
        # self.part_refs = [p.strip() for p in self.parts.ctrl.GetValue().split(',')]
        selected_units = self.GetUnits()
        num_re = self.nums.ctrl.GetValue()
        name_re = self.names.ctrl.GetValue()
        for part in GetBoard().GetModules():
            ref = part.GetReference()
            if self.part_refs and (ref not in self.part_refs):
                continue
            try:
                symbol = self.symbols[ref]
            except KeyError:
                continue
            for pad in part.Pads():
                pin = symbol.pins[pad.GetName()]
                if pin.unit in selected_units and re.search(num_re, pin.num) and re.search(name_re, pin.name) and pin.func in self.selected_pin_funcs:
                    pad.ClearBrightened()
        Refresh()

    def OnDone(self, evt):
        '''Close GUI when Done button is clicked.'''
        self.Close()

    def HandlePinFuncBtns(self, evt):
        '''Handle checking/unchecking pin function checkboxes.'''

        ckbx = evt.GetEventObject()  # Get the checkbox that was clicked.

        # If the All box was checked, then check all the pin function boxes.
        # But if the None box was checked, then uncheck all the pin function boxes.
        if ckbx is self.all_ckbx:
            if self.all_ckbx.GetValue():
                for cb in self.pin_func_btns.values():
                    cb.SetValue(True)
        elif ckbx is self.none_ckbx:
            if self.none_ckbx.GetValue():
                for cb in self.pin_func_btns.values():
                    cb.SetValue(False)

        # Get the checked/unchecked status of all the pin function boxes.
        btn_values = [btn.GetValue() for btn in self.pin_func_btns.values()]

        # Update the All and None checkboxes based on the state of the
        # pin function checkboxes:
        # 1) If all the boxes are checked, then check the All checkbox.
        # 2) If none of the boxes are checked, then check the None checkbox.
        # 3) Otherwise, uncheck both the All and None checkboxes.
        if all(btn_values):
            self.all_ckbx.SetValue(True)
            self.none_ckbx.SetValue(False)
        elif not any(btn_values):
            self.all_ckbx.SetValue(False)
            self.none_ckbx.SetValue(True)
        else:
            self.all_ckbx.SetValue(False)
            self.none_ckbx.SetValue(False)

        self.selected_pin_funcs = [self.pin_func_btn_lbls[btn.GetLabel()] for btn in self.pin_func_btns.values() if btn.GetValue()]

class PadPainter(ActionPlugin):
    def defaults(self):
        self.name = "Pad Painter"
        self.category = "Layout"
        self.description = "Brightens part pads that meet a set of conditions."

    def Run(self):
        frame = PadPainterFrame('Pad Painter')
        frame.Show(True)
        return True


PadPainter().register()
