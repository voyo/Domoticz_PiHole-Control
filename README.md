# Domoticz Pi-hole Control Plugin

Monitor Pi-hole stats and control block lists from Domoticz. Built for Pi-hole v6 API.

Idea based on abandoned plugin by [Xorfor](https://forum.domoticz.com/viewtopic.php?t=20834).

## What it does

- Shows DNS queries, blocked ads, percentage blocked
- Creates switches for each block list
- Auto-syncs when you add/remove lists in Pi-hole
- Works with Pi-hole groups (e.g., Kids group for parental controls)

## Installation
```bash
cd ~/domoticz/plugins
git clone https://github.com/voyo/Domoticz_PiHole-Control.git PiHole
restart domoticz
```

## Setup

1. Go to **Setup → Hardware**
2. Add type: **Pi-hole Monitor and Control**
3. Fill in:
   - **Pi-hole URL**: `http://192.168.0.12` (or `http://pi.hole`)
   - **Password**: Your Pi-hole web interface password (API token)
   - **Update Interval**: 60 seconds (default)

**Important**: Use the actual web interface password, not the hash from setupVars.conf.

Configure and enable an app password via https://pi.hole/admin/settings/api Settings | Web Interface - API in Expert mode and enter that into the local doc page.


## Usage

### Statistics Devices

The plugin creates these read-only devices:
- DNS Queries Today
- Ads Blocked Today
- Ads Percentage
- Domains in Blocklist
- Queries Forwarded/Cached
- Unique Clients/Domains

### Block List Controls

Each block list becomes a switch in Domoticz. Use them with the scheduler for ie. parental controls:

**Example schedule:**
- 06:00 - Enable "List: Kids - Social Media"
- 20:00 - Disable "List: Kids - Social Media"

Lists are named: `List: [comment] ([group])`

## Requirements

- Domoticz 2020.2 or newer
- Pi-hole v6.x
- Python 3

Tested on:
- Pi-hole v6.1.2, FTL v6.2.3, Web v6.2.1
- Domoticz 2024.7

## Credits

- Original concept: [Xorfor](https://forum.domoticz.com/viewtopic.php?t=20834)
- Author: Wojtek Sawasciuk <voyo@no-ip.pl>

## License

Apache-2.0

