# Smart IR Remote Config for Unionaire and Premium Air Conditioner
[![Build Status](https://travis-ci.org/smartHomeHub/SmartIR.svg?branch=master)](https://travis-ci.org/smartHomeHub/SmartIR)
![GitHub release](https://img.shields.io/github/release/smartHomeHub/SmartIR.svg)

## Introduction

This is a custom configuration for Home Assistant to integrate with the Smart IR Remote component. It allows you to control your Unionaire and Premium Air Conditioner with Home Assistant.
## Installation
Add the configuration json file to your custom_components/smartir/climate folder.
## Configuration
Add the following to your configuration.yaml file:
```yaml
climate:
  - platform: smartir
    name: Main AC
    unique_id: main_ac
    device_code: 2140
    controller_data: remote.mbr_broadlink_remote
    temperature_sensor: sensor.temperature_sensor
    humidity_sensor: sensor.humidity_sensor
    power_sensor: binary_sensor.power_sensor
    power_sensor_restore_state: True

```

### Info
Note that this configuration is tested on a Premium Inverter Split System Air Conditioner. It may work on other models as well.

### Configuration variables
The power_sensor_restore_state is used to restore the state of the power sensor after a restart of Home Assistant. This is required because the power sensor is not updated when the AC is turned off.

### Supported models
- Unionaire
- Premium

### Supported functions 
- Power
- Mode
- Fan speed
- Temperature
- Swing

### Supported controllers
- Broadlink

