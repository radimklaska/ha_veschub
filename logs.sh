#!/bin/bash
# Tail HA logs filtered for veschub
ssh hassio@192.168.1.10 "tail -f /config/home-assistant.log | grep --line-buffered veschub"
