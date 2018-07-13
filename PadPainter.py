# -*- coding: utf-8 -*-

# MIT license
#
# Copyright (C) 2018 by XESS Corp.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from pcbnew import * # Pcbnew-KiCad library channel.

import sys, os, os.path # OS and directories.
import re
import wx
import wx.lib.filebrowsebutton as FBB

import traceback

WIDGET_SPACING = 5


def debug_dialog(msg, exception=None):
    if exception:
        msg = '\n'.join((msg, str(exception), traceback.format.exc()))
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

    def __init__(self, parent, label, value, tooltip=''):
        wx.BoxSizer.__init__(self, wx.HORIZONTAL)
        self.lbl = wx.StaticText(parent=parent, label=label)
        self.ctrl = wx.TextCtrl(
            parent=parent, value=value, style=wx.TE_PROCESS_ENTER)
        self.ctrl.SetToolTip(wx.ToolTip(tooltip))
        self.AddSpacer(WIDGET_SPACING)
        self.Add(self.lbl, 0, wx.ALL | wx.ALIGN_CENTER)
        self.AddSpacer(WIDGET_SPACING)
        self.Add(self.ctrl, 1, wx.ALL | wx.EXPAND)
        self.AddSpacer(WIDGET_SPACING)


class LabelledListBox(wx.BoxSizer):
    '''ListBox with label.'''

    def __init__(self, parent, label, choices, tooltip=''):
        wx.BoxSizer.__init__(self, wx.HORIZONTAL)
        self.lbl = wx.StaticText(parent=parent, label=label)
        self.lbx = wx.ListBox(
            parent=parent,
            choices=choices,
            style=wx.LB_EXTENDED | wx.LB_NEEDED_SB | wx.LB_SORT,
            size=wx.Size(1, 50))
        self.lbx.SetToolTip(wx.ToolTip(tooltip))
        self.AddSpacer(WIDGET_SPACING)
        self.Add(self.lbl, 0, wx.ALL | wx.ALIGN_TOP)
        self.AddSpacer(WIDGET_SPACING)
        self.Add(self.lbx, 1, wx.ALL | wx.EXPAND)
        self.AddSpacer(WIDGET_SPACING)


class Part(object):
    '''Object for storing part symbol data.'''
    pass


class Pin(object):
    '''Object for storing pin data.'''
    pass


def get_parts_from_netlist(netlist_file):
    '''Get part information from a netlist file.'''

    # Get the local and global files that contain the symbol tables.
    # Place the global file first so its entries will be overridden by any
    # matching entries in the local file.
    sym_lib_tbl_files = []  # Store the symbol table file paths here.
    brd_file = GetBoard().GetFileName()
    brd_dir = os.path.abspath(os.path.dirname(brd_file))
    brd_name = os.path.splitext(os.path.basename(brd_file))[0]
    if sys.platform == 'win32':
        default_home = os.path.expanduser(r'~\AppData\Roaming\kicad')
    else:
        default_home = os.path.expanduser(r'~/.config/kicad')
    dirs = [os.environ.get('KICAD_CONFIG_HOME', default_home), brd_dir]
    for dir in dirs:
        sym_lib_tbl_file = os.path.join(dir, 'sym-lib-table')
        if os.path.isfile(sym_lib_tbl_file):
            sym_lib_tbl_files.append(sym_lib_tbl_file)

    # Regular expression for getting the symbol library name and file location
    # from the symbol table file.
    sym_tbl_re = '\(\s*lib\s+\(\s*name\s+([^)]+)\s*\).*\(\s*uri\s+([^)]+)\s*\)'

    # Process the global and local symbol library tables to create a dict
    # of the symbol library names and their file locations.
    sym_lib_files = {}
    for tbl_file in sym_lib_tbl_files:
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
        file_name = os.path.join(brd_dir, lib_name + '.lib')
        if os.path.isfile(file_name):
            sym_lib_files[lib_name.lower()] = file_name

    # Regular expressions for getting the part reference and symbol library
    # from the netlist file.
    comp_ref_re = '\(\s*comp\s+\(\s*ref\s+([_A-Za-z][_A-Za-z0-9]*)\s*\)'
    comp_lib_re = '\(\s*libsource\s+\(\s*lib\s+([^)]+)\s*\)\s+\(\s*part\s+([^)]+)\s*\)\s*\)'

    # Scan through the netlist searching for the part references and libraries.
    parts = {}
    with open(netlist_file, 'r') as fp:
        for line in fp:

            # Search for part reference.
            srch_result = re.search(comp_ref_re, line)
            if srch_result:
                ref = srch_result.group(1)
                parts[ref] = None  # Create a dict entry to hold the part.
                continue  # Reference found, so continue with next line.

            # Search for symbol library associated with the part reference.
            srch_result = re.search(comp_lib_re, line)
            if srch_result:
                part = Part()
                part.lib = srch_result.group(1).lower()
                part.part = srch_result.group(2)
                part.ref = ref
                parts[ref] = part
                continue  # Library found, so continue with next line.

    # For each symbol, store the path to the file associated with that symbol's library.
    for part in parts.values():
        if part:
            part.lib_file = sym_lib_files.get(part.lib, None)

    return parts


def fillin_part_info_from_lib(ref, parts):
    '''Fill-in part information from its associated library file.'''

    try:
        part = parts[ref]
    except Exception:
        debug_dialog(ref + ' was not found in the netlist!')
        raise Exception(ref + ' was not found in the netlist!')

    part.pins = {}  # Store part's pin information here.
    part.units = set()  # Store list of part's units here.

    # Abort with empty pins and units if the part's library file was not found.
    if not part.lib_file:
        debug_dialog('Part {} uses library {} that is not in the sym-lib-table file'.format(part.ref, part.lib))
        return

    # Find the part in the library and get the info for each pin.
    with open(part.lib_file, 'r') as fp:
        part_found = False
        for line in fp:
            if part_found:
                if line.startswith('ENDDEF'):
                    # Found the end of the desired part def, so we're done.
                    break

                if line.startswith('X '):
                    # Read pin information records once the desired part def is found.
                    pin_info = line.split()
                    pin = Pin()
                    pin.num = pin_info[2]
                    pin.name = pin_info[1]
                    pin.func = pin_info[11]
                    pin.unit = pin_info[9]
                    part.pins[pin.num] = pin
                    part.units.add(pin.unit)

                continue

            # Look for the start of the desired part's definition.
            part_found = (re.search(r'^DEF\s+' + part.part + r'\s+', line) or
                re.search(r'^ALIAS\s+([^\s]+\s+)*' + part.part + r'\s+', line))


def get_project_directory():
    '''Return the path of the PCB directory.'''
    return os.path.dirname(GetBoard().GetFileName())


def guess_netlist_file():
    '''Try to find the netlist file for this PCB.'''

    design_name = os.path.splitext(os.path.abspath(
        GetBoard().GetFileName()))[0]
    netlist_file_name = design_name + '.net'
    if os.path.isfile(netlist_file_name):
        return netlist_file_name
    return ''


class menuSelection(wx.Menu):
    '''Menu of the distributor checkbox list. Provide select all, unselect and toggle hotkey.'''
    def __init__( self, parent ):
        '''Constructor. Input: checkboxlist to handle.'''
        super(menuSelection, self).__init__()
        self.list = parent
        mmi = self.Append(wx.NewId(), 'Select &all')
        self.Bind(wx.EVT_MENU, self.selectAll, mmi)
        mmi = self.Append(wx.NewId(), '&Unselect all')
        self.Bind(wx.EVT_MENU, self.unselectAll, mmi)
        mmi = self.Append(wx.NewId(), '&Toggle')
        self.Bind(wx.EVT_MENU, self.toggleAll, mmi)

    def selectAll( self, event ):
        '''Select all distributor that exist.'''
        event.Skip()
        for idx in range(self.list.GetCount()):
            if not self.list.IsChecked(idx):
                self.list.Check(idx)

    def unselectAll( self, event ):
        '''Unselect all distributor that exist.'''
        event.Skip()
        for idx in range(self.list.GetCount()):
            if self.list.IsChecked(idx):
                self.list.Check(idx, False)

    def toggleAll( self, event ):
        '''Toggle all distributor that exist.'''
        event.Skip()
        for idx in range(self.list.GetCount()):
            if self.list.IsChecked(idx):
                self.list.Check(idx, False)
            else:
                self.list.Check(idx)


class PadPainterFrame(wx.Frame):
    def __init__(self, title):
        '''Create the GUI for the pad painter.'''

        wx.Frame.__init__(self, None, title=title, pos=(150, 150))

        # Main panel holding all the widgets.
        panel = wx.Panel(parent=self)

        # File browser widget for getting netlist file for this layout.
        netlist_file_wildcard = 'Netlist File|*.net|All Files|*.*'
        self.netlist_file_picker = DnDFilePickerCtrl(
            parent=panel,
            labelText='Netlist File:',
            buttonText='Browse',
            toolTip=
            'Drag-and-drop netlist file associated with this layout or browse for file or enter file name.',
            dialogTitle='Select netlist file associated with this layout',
            startDirectory=get_project_directory(),
            initialValue=guess_netlist_file(),
            fileMask=netlist_file_wildcard,
            fileMode=wx.FD_OPEN)
        self.Bind(wx.EVT_FILEPICKER_CHANGED, self.UpdateUnits,
                  self.netlist_file_picker)

        # Widget for specifying which parts to paint. It starts off preloaded
        # with any parts that have already been selected in the PCBNEW layout.
        selected_parts = ','.join([
            p.GetReference() for p in GetBoard().GetModules()
            if p.IsSelected()
        ])
        self.part_refs = LabelledTextCtrl(
            parent=panel,
            label='Parts:',
            value=selected_parts,
            tooltip=
            "Enter a single part reference or multiple, comma-separated references to paint. Then press 'ENTER'."
        )
        self.Bind(wx.EVT_TEXT_ENTER, self.UpdateUnits, self.part_refs.ctrl)

        # Widget for specifying the units in the parts that will be painted.
        self.units = LabelledListBox(
            parent=panel,
            label='Units:',
            choices=[],
            tooltip=
            "Select one or more units in the part to paint.\n(Use shift-click and ctrl-click to select multiple units.)"
        )

        # Widget for specifying the pin numbers in the parts that will be painted.
        self.nums = LabelledTextCtrl(
            parent=panel,
            label='Pin Numbers:',
            value='.*',
            tooltip="Enter regular expression to select pin numbers to paint.")

        # Widget for specifying the pin names in the parts that will be painted.
        self.names = LabelledTextCtrl(
            parent=panel,
            label='Pin Names:',
            value='.*',
            tooltip="Enter regular expression to select pin names to paint.")

        # Checkboxes for selecting which functional types of pins will be painted.
        self.pin_func_btn_lbls = {
            'In': 'I',
            'Out': 'O',
            'I/O': 'B',
            '3-State': 'T',
            'Pwr': 'W',
            'Pwr Out': 'w',
            'Passive': 'P',
            'Unspec': 'U',
            'OpenColl': 'C',
            'OpenEmit': 'E',
            'NC': 'N',
        }
        pin_func_sizer = wx.StaticBoxSizer(wx.StaticBox(panel, wx.ID_ANY, u"Pin Functions:"), wx.VERTICAL)
        self.pin_func_list = wx.CheckListBox(panel, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, sorted(list(self.pin_func_btn_lbls)), 0)
        self.pin_func_list.SetToolTip(wx.ToolTip(u"Check to disable painting of all functional pin types.\nClick rigth to (un)selection all." ))
        for item in range(self.pin_func_list.GetCount()):
            self.pin_func_list.Check(item) # Start with all checked.
        self.pin_func_list.Bind(wx.EVT_RIGHT_DOWN, self.pin_func_list_rClick)
        pin_func_sizer.Add(self.pin_func_list, 0, wx.ALL, 5 )


        # Checkboxes for selecting the state of the pins.
        self.pin_state_btn_lbls = {
            'Connected': 'C',
            'Unconnected': 'U',
        }
        self.pin_state_btns = {
            lbl: wx.CheckBox(panel, label=lbl)
            for lbl in self.pin_state_btn_lbls
        }
        for btn_lbl, btn in self.pin_state_btns.items():
            btn.SetLabel(btn_lbl)
            btn.SetValue(True)
            btn.SetToolTip(wx.ToolTip(
                    "Check to enable painting of pins that are {} to nets.".format(btn_lbl.lower())
                ))

        # Action buttons for painting and clearing the selected pads.
        self.paint_btn = wx.Button(panel, -1, 'Paint')
        self.paint_btn.SetToolTip(
            wx.ToolTip('Click to paint selected pads on the PCB.'))
        self.clear_btn = wx.Button(panel, -1, 'Clear')
        self.clear_btn.SetToolTip(
            wx.ToolTip('Click to erase paint from selected pads on the PCB.'))
        self.done_btn = wx.Button(panel, -1, 'Done')
        self.done_btn.SetToolTip(
            wx.ToolTip('Click when finished. Any painted pads will remain.'))
        self.Bind(wx.EVT_BUTTON, self.OnPaint, self.paint_btn)
        self.Bind(wx.EVT_BUTTON, self.OnClear, self.clear_btn)
        self.Bind(wx.EVT_BUTTON, self.OnDone, self.done_btn)

        # Create a horizontal sizer for holding all the pin-state checkboxes.
        pin_state_sizer = wx.BoxSizer(wx.HORIZONTAL)
        pin_state_sizer.AddSpacer(WIDGET_SPACING)
        pin_state_sizer.Add(
            wx.StaticText(panel, label='Pin State:'),
            flag=wx.ALL | wx.ALIGN_CENTER)
        pin_state_sizer.AddSpacer(WIDGET_SPACING)
        pin_state_sizer.Add(
            self.pin_state_btns['Connected'], flag=wx.ALL | wx.ALIGN_CENTER)
        pin_state_sizer.AddSpacer(WIDGET_SPACING)
        pin_state_sizer.Add(
            self.pin_state_btns['Unconnected'], flag=wx.ALL | wx.ALIGN_CENTER)
        pin_state_sizer.AddSpacer(WIDGET_SPACING)

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
        sizer.Add(self.part_refs, 0, wx.ALL | wx.EXPAND, WIDGET_SPACING)
        sizer.Add(self.units, 0, wx.ALL | wx.EXPAND, WIDGET_SPACING)
        sizer.Add(self.nums, 0, wx.ALL | wx.EXPAND, WIDGET_SPACING)
        sizer.Add(self.names, 0, wx.ALL | wx.EXPAND, WIDGET_SPACING)
        sizer.Add(pin_state_sizer, 0, wx.ALL, WIDGET_SPACING)
        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, WIDGET_SPACING)

        # Create a horizontal sizer to hold the vertical sizer above and the pin types.
        sizer0 = wx.BoxSizer(wx.HORIZONTAL)
        sizer0.Add(sizer, 0, wx.ALL | wx.ALIGN_CENTER, WIDGET_SPACING)
        sizer0.Add(pin_func_sizer, 0, wx.ALL, WIDGET_SPACING)

        # Create the main vertical sizer.
        sizer00 = wx.BoxSizer(wx.VERTICAL)
        sizer00.Add(self.netlist_file_picker, 0, wx.ALL | wx.EXPAND,
                  WIDGET_SPACING)
        sizer00.Add(sizer0, 0, wx.ALL | wx.EXPAND, WIDGET_SPACING)

        # Size the panel.
        panel.SetSizer(sizer00)
        panel.Layout()
        panel.Fit()

        # Finally, size the frame that holds the panel.
        self.Fit()

    def pin_func_list_rClick(self, event):
        ''' Open the context menu with distributors options.'''
        try:
            menu = menuSelection(self.pin_func_list)
            self.PopupMenu(menu, event.GetPosition())
            menu.Destroy()
        except Exception as e:
            debug_dialog(str(e))

    def UpdateUnits(self, evt):
        '''Update the list of part units from the selected parts.'''

        self.parts = get_parts_from_netlist(self.netlist_file_picker.GetPath())
        part_refs = [
            p.strip() for p in self.part_refs.ctrl.GetValue().split(',') if p
        ]
        for ref in part_refs:
            fillin_part_info_from_lib(ref, self.parts)

        units = set()
        for ref in part_refs:
            units |= self.parts[ref].units

        self.units.lbx.Clear()
        self.units.lbx.InsertItems(list(units), 0)
        for i in range(self.units.lbx.GetCount()):
            self.units.lbx.SetSelection(i)

    def SelectPads(self):
        '''Return a list of PCB pads that meet the selection criteria set in the GUI.'''

        # Get the criteria for selecting pads.
        # Create a list of selected part units.
        lbx = self.units.lbx
        selected_units = [lbx.GetString(i) for i in lbx.GetSelections()]
        # Get the regular expressions for selecting pad numbers and names.
        num_re = self.nums.ctrl.GetValue()
        name_re = self.names.ctrl.GetValue()
        # Create a list of selected part references.
        part_refs = [
            p.strip() for p in self.part_refs.ctrl.GetValue().split(',') if p
        ]
        # Create a list of enabled pin functions.
        selected_pin_funcs = [
            self.pin_func_btn_lbls[self.pin_func_list.GetString(i)]
            for i in range(self.pin_func_list.GetCount())
                if self.pin_func_list.IsChecked(i)
        ]
        # Create a list of enabled pin states.
        selected_pin_states = [
            self.pin_state_btn_lbls[btn.GetLabel()]
            for btn in self.pin_state_btns.values() if btn.GetValue()
        ]

        # Go through the pads and select those that meet the criteria.
        selected_pads = []
        try:
            for part in GetBoard().GetModules():
                ref = part.GetReference()
                if ref not in part_refs:
                    continue
                try:
                    symbol = self.parts[ref]
                except KeyError:
                    continue
                for pad in part.Pads():
                    try:
                        pin = symbol.pins[pad.GetName()]
                        if pad.GetNet().GetNetname().strip() == '':
                            pin.state = 'U'
                        else:
                            pin.state = 'C'
                    except KeyError:
                        # This usually happens when the footprint has a mounting
                        # hole that's not associated with a pin in the electrical symbol.
                        continue
                    if (pin.unit in selected_units and re.search(num_re, pin.num)
                            and re.search(name_re, pin.name)
                            and pin.func in selected_pin_funcs
                            and pin.state in selected_pin_states):
                        selected_pads.append(pad)
        except Exception as e:
            debug_dialog('Something went wrong while selecting pads!', e)

        # Return the selected pads.
        return selected_pads

    def OnPaint(self, evt):
        '''Paint the specified pads.'''
        for pad in self.SelectPads():
            pad.SetBrightened()
        Refresh()

    def OnClear(self, evt):
        '''Clear the specified pads.'''
        for pad in self.SelectPads():
            pad.ClearBrightened()
        Refresh()

    def OnDone(self, evt):
        '''Close GUI when Done button is clicked.'''
        self.Close()


class PadPainter(ActionPlugin):
    def defaults(self):
        self.name = "PadPainter"
        self.category = "Layout"
        self.description = "Highlights part pads that meet a set of conditions."

    def Run(self):
        frame = PadPainterFrame('PadPainter')
        frame.Show(True)
        return True


PadPainter().register()
