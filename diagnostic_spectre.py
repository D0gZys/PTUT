#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic du parsing des trames spectre IC-705
===============================================
Ce script analyse les trames spectre (0x27) pour vérifier
qu'il n'y a pas de décalage entre les données reçues et affichées.

Structure d'une trame spectre 0x27:
-----------------------------------
[0-1]   FE FE       : Préambule
[2]     E0          : Adresse destination (PC)
[3]     A4          : Adresse source (IC-705)
[4]     27          : Commande (spectre)
[5-9]   5 octets    : Fréquence centrale BCD
[10-11] 2 octets    : Information span/step
[12]    1 octet     : Mode/Scope ON/OFF
[13]    1 octet     : Division de trame (numéro de segment)
[14]    1 octet     : Mode de scope (CENTER/FIXED/SCROLL-C/SCROLL-F)
[15]    1 octet     : Référence bas (low)
[16]    1 octet     : Référence haut (high)
[17]    1 octet     : Informations supplémentaires
[18]    1 octet     : Informations supplémentaires
[19+]   Données     : Amplitudes spectrales (jusqu'à FD-1)
[-1]    FD          : Terminateur
"""

import socket
import time
import struct

HOST = '127.0.0.1'
PORT = 50002

def decoder_frequence_bcd(data):
    """Décode une fréquence en BCD (5 octets) vers Hz."""
    if len(data) < 5:
        return 0
    
    freq_hz = 0
    for i, byte in enumerate(data[:5]):
        low = byte & 0x0F
        high = (byte >> 4) & 0x0F
        factor = 10 ** (i * 2)
        freq_hz += low * factor + high * factor * 10
    
    return freq_hz

def analyser_trame_spectre(msg):
    """Analyse en détail une trame spectre 0x27."""
    if len(msg) < 20 or msg[4] != 0x27:
        return None
    
    print(f"\n{'='*60}")
    print(f"ANALYSE TRAME SPECTRE - {len(msg)} octets")
    print(f"{'='*60}")
    
    # En-tête
    print(f"\n[EN-TÊTE]")
    print(f"  Préambule     : {msg[0]:02X} {msg[1]:02X}")
    print(f"  Destination   : {msg[2]:02X} (PC)")
    print(f"  Source        : {msg[3]:02X} (IC-705)")
    print(f"  Commande      : {msg[4]:02X} (SPECTRE)")
    
    # Métadonnées (octets 5-18)
    print(f"\n[MÉTADONNÉES] Octets 5-18")
    
    # Fréquence (octets 5-9)
    freq_hz = decoder_frequence_bcd(msg[5:10])
    freq_mhz = freq_hz / 1_000_000
    print(f"  Fréquence     : {freq_mhz:.6f} MHz ({freq_hz} Hz)")
    print(f"    → BCD brut  : {msg[5]:02X} {msg[6]:02X} {msg[7]:02X} {msg[8]:02X} {msg[9]:02X}")
    
    # Informations span/step (octets 10-11)
    span_info = msg[10:12]
    print(f"  Span/Step     : {span_info[0]:02X} {span_info[1]:02X}")
    
    # Mode scope (octet 12)
    scope_mode = msg[12]
    scope_modes = {0x00: "OFF", 0x01: "ON"}
    print(f"  Scope ON/OFF  : {scope_mode:02X} ({scope_modes.get(scope_mode, '?')})")
    
    # Division de trame / numéro de segment (octet 13)
    # Format: bits 7-4 = division (ex: 11 = 12 segments), bits 3-0 = numéro actuel
    division_byte = msg[13]
    num_divisions = ((division_byte >> 4) & 0x0F) + 1
    segment_num = (division_byte & 0x0F) + 1
    print(f"  Division      : {division_byte:02X}")
    print(f"    → Nombre de segments : {num_divisions}")
    print(f"    → Segment actuel     : {segment_num}/{num_divisions}")
    
    # Mode de scope (octet 14)
    scope_type = msg[14]
    scope_types = {
        0x00: "CENTER",
        0x01: "FIXED",
        0x02: "SCROLL-C",
        0x03: "SCROLL-F"
    }
    print(f"  Type scope    : {scope_type:02X} ({scope_types.get(scope_type, '?')})")
    
    # Références (octets 15-16)
    ref_low = msg[15]
    ref_high = msg[16]
    print(f"  Référence bas : {ref_low:02X} ({ref_low})")
    print(f"  Référence haut: {ref_high:02X} ({ref_high})")
    
    # Octets 17-18
    print(f"  Octet 17      : {msg[17]:02X}")
    print(f"  Octet 18      : {msg[18]:02X}")
    
    # Données d'amplitude
    idx_start = 19
    idx_end = len(msg) - 1  # Avant FD
    donnees = list(msg[idx_start:idx_end])
    
    print(f"\n[DONNÉES D'AMPLITUDE]")
    print(f"  Début         : index {idx_start}")
    print(f"  Fin           : index {idx_end} (avant FD)")
    print(f"  Nombre points : {len(donnees)}")
    print(f"  Min           : {min(donnees)}")
    print(f"  Max           : {max(donnees)}")
    print(f"  Moyenne       : {sum(donnees)/len(donnees):.1f}")
    
    # Premiers et derniers octets
    print(f"\n  5 premiers    : {donnees[:5]}")
    print(f"  5 derniers    : {donnees[-5:]}")
    
    # Terminateur
    print(f"\n[TERMINATEUR]")
    print(f"  Dernier octet : {msg[-1]:02X} (FD)")
    
    return {
        'freq_mhz': freq_mhz,
        'division': num_divisions,
        'segment': segment_num,
        'scope_type': scope_type,
        'nb_points': len(donnees),
        'donnees': donnees
    }

def trouver_messages_civ(buffer):
    """Extrait tous les messages CI-V complets d'un buffer."""
    messages = []
    
    while True:
        debut = buffer.find(bytes([0xFE, 0xFE]))
        if debut == -1:
            buffer.clear()
            break
        
        if debut > 0:
            del buffer[:debut]
        
        fin = buffer.find(bytes([0xFD]))
        if fin == -1:
            break
        
        message = bytes(buffer[:fin + 1])
        messages.append(message)
        del buffer[:fin + 1]
    
    return messages

def main():
    print("="*60)
    print("DIAGNOSTIC DES TRAMES SPECTRE IC-705")
    print("="*60)
    print(f"Connexion: {HOST}:{PORT}\n")
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((HOST, PORT))
        print("✅ Connecté\n")
        
        # Activer le streaming
        cmd = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x1A, 0x05, 0x00, 0x01, 0xFD])
        s.send(cmd)
        print("→ Streaming activé")
        time.sleep(0.3)
        
        # Vider le buffer initial
        s.settimeout(0.1)
        try:
            s.recv(4096)
        except socket.timeout:
            pass
        
        # Recevoir et analyser quelques trames spectre
        buffer = bytearray()
        trames_analysees = 0
        segments_recus = {}  # Pour vérifier si on reçoit tous les segments
        
        print("\nRéception et analyse des trames spectre...")
        print("(Ctrl+C pour arrêter)\n")
        
        s.settimeout(2)
        
        try:
            while trames_analysees < 20:
                try:
                    data = s.recv(4096)
                    buffer.extend(data)
                except socket.timeout:
                    continue
                
                messages = trouver_messages_civ(buffer)
                
                for msg in messages:
                    if len(msg) >= 5 and msg[4] == 0x27:
                        result = analyser_trame_spectre(msg)
                        if result:
                            trames_analysees += 1
                            
                            # Tracker les segments
                            key = (result['freq_mhz'], result['division'])
                            if key not in segments_recus:
                                segments_recus[key] = set()
                            segments_recus[key].add(result['segment'])
                            
                            # Vérifier si tous les segments sont reçus
                            if len(segments_recus[key]) == result['division']:
                                print(f"\n✅ Tous les {result['division']} segments reçus pour {result['freq_mhz']:.3f} MHz")
                        
                        if trames_analysees >= 20:
                            break
        
        except KeyboardInterrupt:
            print("\n\nArrêt par l'utilisateur...")
        
        # Désactiver le streaming
        cmd_off = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x1A, 0x05, 0x00, 0x00, 0xFD])
        s.send(cmd_off)
        
        # Résumé
        print(f"\n{'='*60}")
        print("RÉSUMÉ")
        print(f"{'='*60}")
        print(f"Trames analysées: {trames_analysees}")
        print(f"\nSegments par fréquence:")
        for (freq, div), segs in segments_recus.items():
            print(f"  {freq:.3f} MHz: segments {sorted(segs)} / {div}")
        
        s.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
