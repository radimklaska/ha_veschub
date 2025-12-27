#!/bin/bash
# Tail HA logs filtered for veschub
ssh hassio@192.168.1.10 "sudo docker logs -f homeassistant 2>&1 | grep veschub"
