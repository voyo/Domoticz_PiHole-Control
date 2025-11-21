"""
<plugin key="PiHole" name="Pi-hole Monitor and Control" author="Wojtek Sawasciuk" version="0.0.3" wikilink="https://github.com/voyo/Domoticz_PiHole-Control" externallink="https://pi-hole.net/">
    <description>
        <h2>Pi-hole Monitor and Control Plugin</h2><br/>
        Monitor Pi-hole statistics and control block lists and groups for parental control scheduling.<br/>
        Based on abandoned plugin by Xorfor. Forum thread - https://forum.domoticz.com/viewtopic.php?t=44132
        <h3>Features</h3>
        <ul style="list-style-type:square">
            <li>Real-time Pi-hole statistics monitoring</li>
            <li>Dynamic list detection - automatically adds/removes list devices</li>
            <li>Dynamic group detection - automatically adds/removes group devices</li>
            <li>Individual block list enable/disable control</li>
            <li>Individual group enable/disable control</li>
            <li>Scheduler integration for parental controls</li>
        </ul>
        <h3>Configuration</h3>
        Enter your Pi-hole URL (e.g., http://10.0.20.4 or http://pi.hole) and Web Interface password.
        <h3>Documentation</h3>
        See: <a href="https://github.com/voyo/Domoticz_PiHole-Control">https://github.com/voyo/Domoticz_PiHole-Control</a>
    </description>
    <params>
        <param field="Address" label="Pi-hole URL" width="300px" required="true" default="http://10.0.20.4"/>
        <param field="Password" label="Web Interface Password" width="300px" required="true" password="true" default=""/>
        <param field="Mode1" label="Update Interval (seconds)" width="75px" required="true" default="60"/>
        <param field="Mode6" label="Debug" width="75px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal" default="true"/>
            </options>
        </param>
    </params>
</plugin>
"""

import Domoticz
import json
import urllib.request
import urllib.error
import urllib.parse

class PiHolePlugin:
    
    # Device Unit IDs
    UNIT_DNS_QUERIES = 1
    UNIT_ADS_BLOCKED = 2
    UNIT_ADS_PERCENTAGE = 3
    UNIT_DOMAINS_BLOCKED = 4
    UNIT_QUERIES_FORWARDED = 5
    UNIT_QUERIES_CACHED = 6
    UNIT_CLIENTS_EVER = 7
    UNIT_UNIQUE_CLIENTS = 8
    UNIT_UNIQUE_DOMAINS = 9
    UNIT_STATUS = 10
    UNIT_LISTS_START = 100   # Lists start from unit 100
    UNIT_GROUPS_START = 200  # Groups start from unit 200
    
    def __init__(self):
        self.sid = None
        self.lists_map = {}   # Maps list_id -> unit
        self.groups_map = {}  # Maps group_id -> unit
        self.heartbeat_counter = 0
        return

    def onStart(self):
        Domoticz.Debug("onStart called")
        
        if Parameters["Mode6"] == "Debug":
            Domoticz.Debugging(1)
        
        # Set heartbeat interval
        interval = int(Parameters["Mode1"])
        Domoticz.Heartbeat(interval)
        
        # Create statistics devices if they don't exist
        self.createStatisticsDevices()
        
        # Load existing mappings from Domoticz devices
        self.loadExistingListMappings()
        self.loadExistingGroupMappings()
        
        # Authenticate and sync devices
        if self.authenticate():
            self.syncListDevices()
            self.syncGroupDevices()
            self.updateDevices()
        else:
            Domoticz.Error("Failed to authenticate with Pi-hole")

    def onStop(self):
        Domoticz.Debug("onStop called")

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug("onConnect called")

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called")

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug(f"onCommand called for Unit {Unit}: Command '{Command}', Level: {Level}")
        
        # Handle list enable/disable commands
        if Unit >= self.UNIT_LISTS_START and Unit < self.UNIT_GROUPS_START:
            list_id = self.getListIdFromUnit(Unit)
            if list_id:
                new_state = (Command.upper() == "ON")
                if self.setListState(list_id, new_state):
                    # Update device state
                    nValue = 1 if new_state else 0
                    sValue = "On" if new_state else "Off"
                    Devices[Unit].Update(nValue=nValue, sValue=sValue)
                    Domoticz.Log(f"List ID {list_id} ('{Devices[Unit].Name}') set to {'enabled' if new_state else 'disabled'}")
                    
                    # Force immediate refresh after state change
                    self.updateDevices()
                else:
                    Domoticz.Error(f"Failed to change state of list ID {list_id}")
        
        # Handle group enable/disable commands
        elif Unit >= self.UNIT_GROUPS_START:
            group_id = self.getGroupIdFromUnit(Unit)
            if group_id is not None:
                new_state = (Command.upper() == "ON")
                if self.setGroupState(group_id, new_state):
                    # Update device state
                    nValue = 1 if new_state else 0
                    sValue = "On" if new_state else "Off"
                    Devices[Unit].Update(nValue=nValue, sValue=sValue)
                    Domoticz.Log(f"Group ID {group_id} ('{Devices[Unit].Name}') set to {'enabled' if new_state else 'disabled'}")
                    
                    # Force immediate refresh after state change
                    self.updateDevices()
                else:
                    Domoticz.Error(f"Failed to change state of group ID {group_id}")

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Debug("onNotification called")

    def onDisconnect(self, Connection):
        Domoticz.Debug("onDisconnect called")

    def onHeartbeat(self):
        Domoticz.Debug("onHeartbeat called")
        
        # Re-authenticate every 10 heartbeats (session might expire)
        self.heartbeat_counter += 1
        if self.heartbeat_counter >= 10:
            self.heartbeat_counter = 0
            if not self.authenticate():
                Domoticz.Error("Re-authentication failed")
                return
        
        # Sync devices (check for added/removed lists and groups)
        self.syncListDevices()
        self.syncGroupDevices()
        
        # Update all devices
        self.updateDevices()

    def createStatisticsDevices(self):
        """Create statistics monitoring devices"""
        
        # Use Custom Sensor to avoid kWh units
        if self.UNIT_DNS_QUERIES not in Devices:
            Domoticz.Device(Name="DNS Queries Today", Unit=self.UNIT_DNS_QUERIES, 
                          TypeName="Custom", Options={"Custom": "1;queries"}, Used=1).Create()
        
        if self.UNIT_ADS_BLOCKED not in Devices:
            Domoticz.Device(Name="Ads Blocked Today", Unit=self.UNIT_ADS_BLOCKED, 
                          TypeName="Custom", Options={"Custom": "1;blocked"}, Used=1).Create()
        
        if self.UNIT_ADS_PERCENTAGE not in Devices:
            Domoticz.Device(Name="Ads Percentage", Unit=self.UNIT_ADS_PERCENTAGE, 
                          TypeName="Percentage", Used=1).Create()
        
        if self.UNIT_DOMAINS_BLOCKED not in Devices:
            Domoticz.Device(Name="Domains in Blocklist", Unit=self.UNIT_DOMAINS_BLOCKED, 
                          TypeName="Custom", Options={"Custom": "1;domains"}, Used=1).Create()
        
        if self.UNIT_QUERIES_FORWARDED not in Devices:
            Domoticz.Device(Name="Queries Forwarded", Unit=self.UNIT_QUERIES_FORWARDED, 
                          TypeName="Custom", Options={"Custom": "1;queries"}, Used=1).Create()
        
        if self.UNIT_QUERIES_CACHED not in Devices:
            Domoticz.Device(Name="Queries Cached", Unit=self.UNIT_QUERIES_CACHED, 
                          TypeName="Custom", Options={"Custom": "1;queries"}, Used=1).Create()
        
        if self.UNIT_CLIENTS_EVER not in Devices:
            Domoticz.Device(Name="Clients Ever Seen", Unit=self.UNIT_CLIENTS_EVER, 
                          TypeName="Custom", Options={"Custom": "1;clients"}, Used=1).Create()
        
        if self.UNIT_UNIQUE_CLIENTS not in Devices:
            Domoticz.Device(Name="Unique Clients", Unit=self.UNIT_UNIQUE_CLIENTS, 
                          TypeName="Custom", Options={"Custom": "1;clients"}, Used=1).Create()
        
        if self.UNIT_UNIQUE_DOMAINS not in Devices:
            Domoticz.Device(Name="Unique Domains", Unit=self.UNIT_UNIQUE_DOMAINS, 
                          TypeName="Custom", Options={"Custom": "1;domains"}, Used=1).Create()
        
        if self.UNIT_STATUS not in Devices:
            Domoticz.Device(Name="Pi-hole Status", Unit=self.UNIT_STATUS, 
                          TypeName="Switch", Switchtype=0, Used=1).Create()

    def loadExistingListMappings(self):
        """Load existing list ID to unit mappings from device descriptions"""
        for unit, device in Devices.items():
            if unit >= self.UNIT_LISTS_START and unit < self.UNIT_GROUPS_START and device.Description.startswith("ListID:"):
                try:
                    list_id = int(device.Description.split(":")[1])
                    self.lists_map[list_id] = unit
                    Domoticz.Debug(f"Loaded mapping: List ID {list_id} -> Unit {unit}")
                except:
                    pass

    def loadExistingGroupMappings(self):
        """Load existing group ID to unit mappings from device descriptions"""
        for unit, device in Devices.items():
            if unit >= self.UNIT_GROUPS_START and device.Description.startswith("GroupID:"):
                try:
                    group_id = int(device.Description.split(":")[1])
                    self.groups_map[group_id] = unit
                    Domoticz.Debug(f"Loaded mapping: Group ID {group_id} -> Unit {unit}")
                except:
                    pass

    def syncListDevices(self):
        """Synchronize list devices with Pi-hole - add new, remove deleted, update names"""
        
        Domoticz.Debug("=== Starting list synchronization ===")
        
        lists_data = self.apiGet("/lists")
        if not lists_data or 'lists' not in lists_data:
            Domoticz.Error("Failed to get lists from Pi-hole")
            return
        
        # Log what we received
        Domoticz.Debug(f"Received {len(lists_data['lists'])} lists from Pi-hole API")
        for lst in lists_data['lists']:
            Domoticz.Debug(f"  Pi-hole list: ID={lst.get('id')}, address={lst.get('address')}, enabled={lst.get('enabled')}")
        
        current_lists = {lst.get('id'): lst for lst in lists_data['lists']}
        current_list_ids = set(current_lists.keys())
        existing_list_ids = set(self.lists_map.keys())
        
        Domoticz.Debug(f"Current Pi-hole list IDs: {sorted(current_list_ids)}")
        Domoticz.Debug(f"Existing Domoticz list IDs: {sorted(existing_list_ids)}")
        
        # Find new lists (in Pi-hole but not in Domoticz)
        new_list_ids = current_list_ids - existing_list_ids
        
        # Find removed lists (in Domoticz but not in Pi-hole)
        removed_list_ids = existing_list_ids - current_list_ids
        
        if new_list_ids:
            Domoticz.Log(f"Found {len(new_list_ids)} new list(s) to add: {new_list_ids}")
        if removed_list_ids:
            Domoticz.Log(f"Found {len(removed_list_ids)} deleted list(s) to remove: {removed_list_ids}")
        
        # Remove deleted lists from Domoticz
        for list_id in removed_list_ids:
            unit = self.lists_map.get(list_id)
            if unit and unit in Devices:
                device_name = Devices[unit].Name
                Domoticz.Log(f"Removing device for deleted list ID {list_id}: {device_name} (Unit {unit})")
                Devices[unit].Delete()
            if list_id in self.lists_map:
                del self.lists_map[list_id]
        
        # Add new lists to Domoticz
        for list_id in new_list_ids:
            lst = current_lists[list_id]
            self.createListDevice(list_id, lst)
        
        # Update existing list names and states (in case comment/group changed)
        for list_id in (existing_list_ids & current_list_ids):
            lst = current_lists[list_id]
            unit = self.lists_map.get(list_id)
            
            if unit and unit in Devices:
                new_name = self.generateListDeviceName(lst)
                if Devices[unit].Name != new_name:
                    old_name = Devices[unit].Name
                    Devices[unit].Update(Name=new_name, nValue=Devices[unit].nValue, 
                                       sValue=Devices[unit].sValue)
                    Domoticz.Log(f"Updated list name from '{old_name}' to '{new_name}'")
        
        Domoticz.Debug("=== Finished list synchronization ===")

    def syncGroupDevices(self):
        """Synchronize group devices with Pi-hole - add new, remove deleted, update names"""
        
        Domoticz.Debug("=== Starting group synchronization ===")
        
        groups_data = self.apiGet("/groups")
        if not groups_data or 'groups' not in groups_data:
            Domoticz.Error("Failed to get groups from Pi-hole")
            return
        
        # Log what we received
        Domoticz.Debug(f"Received {len(groups_data['groups'])} groups from Pi-hole API")
        for grp in groups_data['groups']:
            Domoticz.Debug(f"  Pi-hole group: ID={grp.get('id')}, name={grp.get('name')}, enabled={grp.get('enabled')}")
        
        current_groups = {grp.get('id'): grp for grp in groups_data['groups']}
        current_group_ids = set(current_groups.keys())
        existing_group_ids = set(self.groups_map.keys())
        
        Domoticz.Debug(f"Current Pi-hole group IDs: {sorted(current_group_ids)}")
        Domoticz.Debug(f"Existing Domoticz group IDs: {sorted(existing_group_ids)}")
        
        # Find new groups
        new_group_ids = current_group_ids - existing_group_ids
        
        # Find removed groups
        removed_group_ids = existing_group_ids - current_group_ids
        
        if new_group_ids:
            Domoticz.Log(f"Found {len(new_group_ids)} new group(s) to add: {new_group_ids}")
        if removed_group_ids:
            Domoticz.Log(f"Found {len(removed_group_ids)} deleted group(s) to remove: {removed_group_ids}")
        
        # Remove deleted groups from Domoticz
        for group_id in removed_group_ids:
            unit = self.groups_map.get(group_id)
            if unit and unit in Devices:
                device_name = Devices[unit].Name
                Domoticz.Log(f"Removing device for deleted group ID {group_id}: {device_name} (Unit {unit})")
                Devices[unit].Delete()
            if group_id in self.groups_map:
                del self.groups_map[group_id]
        
        # Add new groups to Domoticz
        for group_id in new_group_ids:
            grp = current_groups[group_id]
            self.createGroupDevice(group_id, grp)
        
        # Update existing group names and states
        for group_id in (existing_group_ids & current_group_ids):
            grp = current_groups[group_id]
            unit = self.groups_map.get(group_id)
            
            if unit and unit in Devices:
                new_name = f"Group: {grp.get('name', 'Unnamed Group')}"
                if Devices[unit].Name != new_name:
                    old_name = Devices[unit].Name
                    Devices[unit].Update(Name=new_name, nValue=Devices[unit].nValue, 
                                       sValue=Devices[unit].sValue)
                    Domoticz.Log(f"Updated group name from '{old_name}' to '{new_name}'")
        
        Domoticz.Debug("=== Finished group synchronization ===")

    def generateListDeviceName(self, lst):
        """Generate device name for a list"""
        comment = lst.get('comment', 'Unnamed List')
        groups = lst.get('groups', [])
        
        # Group names mapping
        group_names = {0: "Default", 1: "Kids"}
        if groups:
            group_str = ', '.join(group_names.get(g, f"Group {g}") for g in groups)
            return f"List: {comment} ({group_str})"
        else:
            return f"List: {comment}"

    def createListDevice(self, list_id, lst):
        """Create a new device for a block list"""
        
        device_name = self.generateListDeviceName(lst)
        enabled = lst.get('enabled', False)
        
        # Find next available unit in lists range
        unit = self.UNIT_LISTS_START
        while unit in Devices or unit in self.lists_map.values():
            unit += 1
            if unit >= self.UNIT_GROUPS_START:
                Domoticz.Error("No available units for lists")
                return
        
        # Store list_id in device description for persistence
        description = f"ListID:{list_id}"
        
        Domoticz.Device(Name=device_name, Unit=unit, 
                      TypeName="Switch", Switchtype=0, 
                      Description=description, Used=1).Create()
        
        # Update mapping
        self.lists_map[list_id] = unit
        
        # Set initial state
        nValue = 1 if enabled else 0
        sValue = "On" if enabled else "Off"
        Devices[unit].Update(nValue=nValue, sValue=sValue)
        
        Domoticz.Log(f"Created device for list ID {list_id}: {device_name} (Unit {unit})")

    def createGroupDevice(self, group_id, grp):
        """Create a new device for a group"""
        
        device_name = f"Group: {grp.get('name', 'Unnamed Group')}"
        enabled = grp.get('enabled', True)
        
        # Find next available unit in groups range
        unit = self.UNIT_GROUPS_START
        while unit in Devices or unit in self.groups_map.values():
            unit += 1
        
        # Store group_id in device description for persistence
        description = f"GroupID:{group_id}"
        
        Domoticz.Device(Name=device_name, Unit=unit, 
                      TypeName="Switch", Switchtype=0, 
                      Description=description, Used=1).Create()
        
        # Update mapping
        self.groups_map[group_id] = unit
        
        # Set initial state
        nValue = 1 if enabled else 0
        sValue = "On" if enabled else "Off"
        Devices[unit].Update(nValue=nValue, sValue=sValue)
        
        Domoticz.Log(f"Created device for group ID {group_id}: {device_name} (Unit {unit})")

    def getListIdFromUnit(self, unit):
        """Get list ID from unit number"""
        for list_id, mapped_unit in self.lists_map.items():
            if mapped_unit == unit:
                return list_id
        return None

    def getGroupIdFromUnit(self, unit):
        """Get group ID from unit number"""
        for group_id, mapped_unit in self.groups_map.items():
            if mapped_unit == unit:
                return group_id
        return None

    def updateDevices(self):
        """Update all device values"""
        
        # Get complete statistics from /stats/summary
        summary = self.apiGet("/stats/summary")
        if not summary or 'queries' not in summary:
            Domoticz.Error("Failed to get statistics from Pi-hole")
            return
        
        queries = summary['queries']
        clients = summary['clients']
        gravity = summary['gravity']
        
        # Extract statistics
        total_queries = queries.get('total', 0)
        blocked_queries = queries.get('blocked', 0)
        ads_percentage = queries.get('percent_blocked', 0)
        unique_domains = queries.get('unique_domains', 0)
        queries_forwarded = queries.get('forwarded', 0)
        queries_cached = queries.get('cached', 0)
        
        # Client statistics
        active_clients = clients.get('active', 0)
        total_clients = clients.get('total', 0)
        
        # Gravity (blocklist) statistics
        domains_blocked = gravity.get('domains_being_blocked', 0)
        
        # Update statistics devices
        self.updateDevice(self.UNIT_DNS_QUERIES, 0, str(total_queries))
        self.updateDevice(self.UNIT_ADS_BLOCKED, 0, str(blocked_queries))
        self.updateDevice(self.UNIT_ADS_PERCENTAGE, 0, f"{ads_percentage:.2f}")
        self.updateDevice(self.UNIT_DOMAINS_BLOCKED, 0, str(domains_blocked))
        self.updateDevice(self.UNIT_QUERIES_FORWARDED, 0, str(queries_forwarded))
        self.updateDevice(self.UNIT_QUERIES_CACHED, 0, str(queries_cached))
        self.updateDevice(self.UNIT_CLIENTS_EVER, 0, str(total_clients))
        self.updateDevice(self.UNIT_UNIQUE_CLIENTS, 0, str(active_clients))
        self.updateDevice(self.UNIT_UNIQUE_DOMAINS, 0, str(unique_domains))
        self.updateDevice(self.UNIT_STATUS, 1, "On")  # Pi-hole is responding
        
        # Update list devices states
        lists_data = self.apiGet("/lists")
        if lists_data and 'lists' in lists_data:
            for lst in lists_data['lists']:
                list_id = lst.get('id')
                if list_id in self.lists_map:
                    unit = self.lists_map[list_id]
                    enabled = lst.get('enabled', False)
                    nValue = 1 if enabled else 0
                    sValue = "On" if enabled else "Off"
                    self.updateDevice(unit, nValue, sValue)
        
        # Update group devices states
        groups_data = self.apiGet("/groups")
        if groups_data and 'groups' in groups_data:
            for grp in groups_data['groups']:
                group_id = grp.get('id')
                if group_id in self.groups_map:
                    unit = self.groups_map[group_id]
                    enabled = grp.get('enabled', True)
                    nValue = 1 if enabled else 0
                    sValue = "On" if enabled else "Off"
                    self.updateDevice(unit, nValue, sValue)

    def updateDevice(self, unit, nValue, sValue):
        """Update device only if value changed"""
        if unit in Devices:
            if Devices[unit].nValue != nValue or Devices[unit].sValue != sValue:
                Devices[unit].Update(nValue=nValue, sValue=sValue)

    def authenticate(self):
        """Authenticate with Pi-hole API"""
        try:
            # Strip trailing slash from URL if present
            base_url = Parameters['Address'].rstrip('/')
            url = f"{base_url}/api/auth"
            
            data = json.dumps({"password": Parameters["Password"]}).encode('utf-8')
            
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            response = urllib.request.urlopen(req, timeout=5)
            
            result = json.loads(response.read().decode('utf-8'))
            
            session = result.get('session', {})
            if not session.get('valid'):
                Domoticz.Error(f"Authentication failed: {session.get('message', 'Unknown error')}")
                return False
            
            self.sid = session.get('sid')
            
            if self.sid:
                Domoticz.Log(f"Authenticated successfully with Pi-hole at {Parameters['Address']}")
                return True
            else:
                Domoticz.Error("Authentication failed: No SID received")
                return False
                
        except Exception as e:
            Domoticz.Error(f"Authentication error: {str(e)}")
            return False

    def apiGet(self, endpoint):
        """Make GET request to Pi-hole API"""
        try:
            # Strip trailing slash from URL if present
            base_url = Parameters['Address'].rstrip('/')
            url = f"{base_url}/api{endpoint}"
            
            req = urllib.request.Request(url)
            
            if self.sid:
                req.add_header('X-FTL-SID', self.sid)
            
            response = urllib.request.urlopen(req, timeout=5)
            return json.loads(response.read().decode('utf-8'))
            
        except urllib.error.HTTPError as e:
            Domoticz.Debug(f"HTTP Error on {endpoint}: {e.code} - {e.reason}")
            return None
        except Exception as e:
            Domoticz.Debug(f"API GET error on {endpoint}: {str(e)}")
            return None

    def setListState(self, list_id, enabled):
        """Enable or disable a block list - Pi-hole v6 API
        Uses PUT on /lists/{address}?type=block with enabled boolean
        Based on: https://discourse.pi-hole.net/t/enable-disable-lists-via-api/82763
        """
        try:
            # Get current list data to find its address
            lists_data = self.apiGet("/lists")
            if not lists_data or 'lists' not in lists_data:
                Domoticz.Error("Failed to get lists data")
                return False
            
            # Find the list by ID to get its address
            target_list = None
            for lst in lists_data['lists']:
                if lst.get('id') == list_id:
                    target_list = lst
                    break
            
            if not target_list:
                Domoticz.Error(f"List ID {list_id} not found")
                return False
            
            list_address = target_list.get('address', '')
            list_type = target_list.get('type', 'block')
            
            if not list_address:
                Domoticz.Error(f"List ID {list_id} has no address")
                return False
            
            # URL encode the address
            encoded_address = urllib.parse.quote(list_address, safe='')
            
            # Strip trailing slash from URL if present
            base_url = Parameters['Address'].rstrip('/')
            
            # PUT to /lists/{encoded_address}?type={type}
            url = f"{base_url}/api/lists/{encoded_address}?type={list_type}"
            
            # Send ALL fields from current list to preserve comment, groups, etc.
            update_data = {
                "enabled": enabled,
                "comment": target_list.get('comment', ''),
                "groups": target_list.get('groups', []),
                "address": list_address,
                "type": list_type
            }
            
            data = json.dumps(update_data).encode('utf-8')
            
            req = urllib.request.Request(url, data=data, method='PUT',
                                        headers={'Content-Type': 'application/json'})
            
            if self.sid:
                req.add_header('X-FTL-SID', self.sid)
            
            response = urllib.request.urlopen(req, timeout=5)
            result = json.loads(response.read().decode('utf-8'))
            
            Domoticz.Debug(f"PUT result: {result}")
            
            # Check for errors
            if 'error' in result:
                Domoticz.Error(f"API error: {result['error']}")
                return False
            
            # Check processed results
            if 'processed' in result:
                errors = result['processed'].get('errors', [])
                if errors:
                    Domoticz.Error(f"Error updating list {list_id}: {errors}")
                    return False
            
            Domoticz.Log(f"Successfully set list {list_id} ('{target_list.get('comment')}') to {'enabled' if enabled else 'disabled'}")
            return True
            
        except urllib.error.HTTPError as e:
            try:
                error_body = e.read().decode('utf-8')
                error_data = json.loads(error_body)
                Domoticz.Error(f"HTTP Error {e.code}: {error_data}")
            except:
                Domoticz.Error(f"HTTP Error {e.code}: {e.reason}")
            return False
        except Exception as e:
            Domoticz.Error(f"Error setting list state: {str(e)}")
            return False

    def setGroupState(self, group_id, enabled):
        """Enable or disable a group - Pi-hole v6 API"""
        try:
            # Get current group data
            groups_data = self.apiGet("/groups")
            if not groups_data or 'groups' not in groups_data:
                Domoticz.Error("Failed to get groups data")
                return False
            
            # Find the group by ID
            target_group = None
            for grp in groups_data['groups']:
                if grp.get('id') == group_id:
                    target_group = grp
                    break
            
            if not target_group:
                Domoticz.Error(f"Group ID {group_id} not found")
                return False
            
            # Strip trailing slash from URL if present
            base_url = Parameters['Address'].rstrip('/')
            
            # PUT to /groups/{id}
            url = f"{base_url}/api/groups/{group_id}"
            
            # Send ALL fields from current group to preserve name, description, etc.
            update_data = {
                "enabled": enabled,
                "name": target_group.get('name', ''),
                "description": target_group.get('description', '')
            }
            
            data = json.dumps(update_data).encode('utf-8')
            
            req = urllib.request.Request(url, data=data, method='PUT',
                                        headers={'Content-Type': 'application/json'})
            
            if self.sid:
                req.add_header('X-FTL-SID', self.sid)
            
            response = urllib.request.urlopen(req, timeout=5)
            result = json.loads(response.read().decode('utf-8'))
            
            Domoticz.Debug(f"PUT result: {result}")
            
            # Check for errors
            if 'error' in result:
                Domoticz.Error(f"API error: {result['error']}")
                return False
            
            # Check processed results
            if 'processed' in result:
                errors = result['processed'].get('errors', [])
                if errors:
                    Domoticz.Error(f"Error updating group {group_id}: {errors}")
                    return False
            
            Domoticz.Log(f"Successfully set group {group_id} ('{target_group.get('name')}') to {'enabled' if enabled else 'disabled'}")
            return True
            
        except urllib.error.HTTPError as e:
            try:
                error_body = e.read().decode('utf-8')
                error_data = json.loads(error_body)
                Domoticz.Error(f"HTTP Error {e.code}: {error_data}")
            except:
                Domoticz.Error(f"HTTP Error {e.code}: {e.reason}")
            return False
        except Exception as e:
            Domoticz.Error(f"Error setting group state: {str(e)}")
            return False

global _plugin
_plugin = PiHolePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

