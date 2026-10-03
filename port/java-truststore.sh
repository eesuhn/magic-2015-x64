#!/bin/bash
# Optional, for networks with TLS inspection (e.g. a Cloudflare Gateway): Java tools (Gradle,
# sdkmanager) ignore the macOS keychain, so they reject the inspection proxy's certificates.
# This writes build/java-truststore.jks = the JDK's CA certificates + the inspection CA taken
# from the System keychain. port/build.sh uses it automatically when it exists.
#
#   port/java-truststore.sh ["Gateway CA - Cloudflare Managed"]
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
CA_NAME=${1:-"Gateway CA - Cloudflare Managed"}
OUT=$ROOT/build/java-truststore.jks
JAVA_HOME=${JAVA_HOME:-$(/usr/bin/java -XshowSettings:properties -version 2>&1 | awk -F'= ' '/java.home/{print $2}')}

mkdir -p "$ROOT/build"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
security find-certificate -a -c "$CA_NAME" -p /Library/Keychains/System.keychain > "$tmp/ca.pem" 2>/dev/null || true
[ -s "$tmp/ca.pem" ] || { echo "no certificate named '$CA_NAME' in the System keychain" >&2; exit 1; }

# The keychain CA must be the one the network actually presents.
served=$(echo | openssl s_client -connect dl.google.com:443 -servername dl.google.com -showcerts 2>/dev/null |
    awk '/BEGIN CERT/{n++} n==2' | openssl x509 -noout -fingerprint -sha256 2>/dev/null || true)
mine=$(openssl x509 -in "$tmp/ca.pem" -noout -fingerprint -sha256)
[ "$served" = "$mine" ] || { echo "the keychain CA does not match the CA the network presents" >&2; exit 1; }

cp "$JAVA_HOME/lib/security/cacerts" "$OUT"
chmod u+w "$OUT"
keytool -importcert -noprompt -keystore "$OUT" -storepass changeit -alias tls-inspection \
    -file "$tmp/ca.pem" >/dev/null 2>&1
echo "wrote $OUT"
