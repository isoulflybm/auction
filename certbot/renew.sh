#!/bin/sh
set -e

# This script will run in a loop to renew certificates

while :; do
  certbot renew --quiet
  sleep 12h
done
