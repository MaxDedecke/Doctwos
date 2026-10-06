#!/usr/bin/env bash
# Erzeugt THIRD-PARTY-NOTICES.txt fuer das Offline-Bundle (OSS-CLEARING.md,
# "Nicht automatisch geprueft"): Lizenztext, Version und Quellcode-Angebot fuer
# die GPL-lizenzierten Debian-Programme in den ausgelieferten Images (derzeit
# `git`; wird nur als eigener Prozess aufgerufen, nicht gelinkt). Die Angaben
# kommen aus den fertig gebauten Images, damit sie nicht von der
# ausgelieferten Version abweichen.
#
# Aufruf: gen-third-party-notices.sh <ausgabedatei> <image> [<image> ...]
set -euo pipefail

out="$1"; shift
# GPL-Programme, die im Image liegen duerfen (nur per Subprozess genutzt).
gpl_packages="git"
seen=" "

{
    echo "THIRD-PARTY NOTICES — Doctus"
    echo "============================"
    echo
    echo "Die Doctus-Images enthalten neben Doctus-Code und Python-/Node-Bibliotheken"
    echo "(Lizenzuebersicht: OSS-CLEARING.md) Debian-Systempakete. Die folgenden stehen"
    echo "unter der GNU General Public License. Doctus ruft sie nur als eigene Prozesse"
    echo "auf; sie sind weder gelinkt noch veraendert."
    echo
    echo "ANGEBOT ZUR QUELLCODE-ABGABE (GPL-2.0 §3)"
    echo "-----------------------------------------"
    echo "Den vollstaendigen Quellcode der unten genannten Pakete in genau der"
    echo "ausgelieferten Version erhalten Sie fuer mindestens drei Jahre ab Auslieferung"
    echo "auf Anfrage bei Ihrem Doctus-Ansprechpartner. Er ist ausserdem oeffentlich bei"
    echo "Debian verfuegbar: 'apt-get source <paket>=<version>' bzw."
    echo "https://snapshot.debian.org/ und https://sources.debian.org/."
    echo
    for image in "$@"; do
        for pkg in $gpl_packages; do
            version=$(docker run --rm --entrypoint dpkg-query "$image" -W -f='${Version}' "$pkg" 2>/dev/null || true)
            [ -n "$version" ] || continue
            # Gleiche Paketversion in mehreren Images nur einmal auffuehren.
            case "$seen" in *" $pkg=$version "*) continue ;; esac
            seen="$seen$pkg=$version "
            echo "== Image(s) mit $pkg $version, erstmals: $image"
            docker run --rm --entrypoint cat "$image" "/usr/share/doc/$pkg/copyright"
            echo
        done
    done
    echo "== Volltext GNU General Public License, Version 2 (Debian /usr/share/common-licenses/GPL-2)"
    first_image="$1"
    docker run --rm --entrypoint cat "$first_image" /usr/share/common-licenses/GPL-2
} > "$out"
