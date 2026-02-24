# Hisense TV Integration for Home Assistant

This is a **fork** of the Hisense TV integration. It lets you control your Hisense TV from Home Assistant using MQTT and Wake-on-LAN.

Requires Home Assistant 2022.10 or newer.

---

## How It Works

Your Hisense TV has a built-in MQTT broker on port **36669**. This integration connects **directly** to that broker. No MQTT bridge is needed.

```
+----------------+     MQTT      +------------------+
| Home Assistant | <------------> | Hisense TV       |
| (this add-on)  |   port 36669  | (built-in broker)|
+----------------+               +------------------+
```

1. **Turn on**: Home Assistant sends a Wake-on-LAN packet to your TV using its MAC address.
2. **Turn off / control**: Home Assistant sends MQTT commands to the TV broker (power, volume, source, etc.).
3. **State**: The integration listens to MQTT messages from the TV and polls it every 30 seconds to know if it is on or off.

---

## Features

- Turn TV on (Wake-on-LAN) and off (power key)
- See current source (TV, HDMI, Apps), channel, and volume
- Volume control and mute
- Media browser (channels, apps)
- ON/OFF switch entity
- Picture settings sensor

---

## Setup

1. Add the integration in Home Assistant (Settings → Devices & Services → Add Integration).
2. Enter your TV’s **IP address** and **MAC address**.
3. During setup, the TV must be **on**. Some TVs ask for a PIN; others use MQTT username/password only.
4. Default MQTT credentials: username `hisenseservice`, password `multimqttservice`, port `36669`.

---

## Tested On

- Hisense H55A6500

---

## Acknowledgments

This integration is based on work by:

- [@sehaas](https://github.com/sehaas/ha_hisense_tv)
- [@Krazy998's mqtt-hisensetv](https://github.com/Krazy998/mqtt-hisensetv)
- [@newAM's hisensetv_hass](https://github.com/newAM/hisensetv_hass)
- [HA Community](https://community.home-assistant.io/t/hisense-tv-control/97638/1)
- [@d3nd3](https://github.com/d3nd3/Hisense-mqtt-keyfiles)
