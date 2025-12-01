#!/usr/bin/env python3
"""
Contrôle IC-705 via CI-V - Streaming des données spectrales
Active le streaming et lit les données du spectre en continu
"""

import socket
import time

HOST = '127.0.0.1'  
PORT = 50002

print("="*60)
print("IC-705 Spectrum Streaming via CI-V")
print("="*60)
print(f"Connexion: {HOST}:{PORT}\n")

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((HOST, PORT))
    print("✅ Connecté au serveur CI-V\n")

    # Commande pour activer le streaming des données spectrales
    # FE FE A4 E0 1A 05 00 01 FD
    # 1A 05 = Set Scope ON/OFF
    # 00 01 = Paramètres (01 = ON, 00 = OFF)
    cmd = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x1A, 0x05, 0x00, 0x01, 0xFD])
    
    print(f"→ Activation du streaming spectral:")
    print(f"   {cmd.hex(' ').upper()}")
    print("   (Set Scope Streaming ON)\n")
    s.send(cmd)
    
    print("Attente de l'acquittement...\n")
    
    # Attendre l'acquittement de l'activation
    response = bytearray()
    start = time.time()
    while time.time() - start < 2:
        byte = s.recv(1)
        if not byte:
            break
        response.extend(byte)
        if byte[0] == 0xFD:
            break
    
    if len(response) > 0:
        print(f"← Réponse: {response.hex(' ').upper()}")
        if len(response) == 6 and response[4] == 0xFB:
            print("✅ Streaming activé avec succès (FB = OK)\n")
        elif len(response) == 6 and response[4] == 0xFA:
            print("❌ Commande refusée (FA = NG)\n")
            s.close()
            exit(1)
    
    print("Lecture des données brutes en continu...")
    print("Appuyez sur Ctrl+C pour arrêter\n")
    
    # Lire les données en continu
    try:
        while True:
            response = bytearray()
            start = time.time()
            
            # Lire un message complet
            while time.time() - start < 5:
                byte = s.recv(1)
                if not byte:
                    break
                response.extend(byte)
                if byte[0] == 0xFD:
                    break
            
            if len(response) == 0:
                continue
            
            # Afficher les données brutes reçues
            print(response.hex(' ').upper())
            
    except KeyboardInterrupt:
        print("\n\nArrêt...")
        
        # Désactiver le streaming avant de fermer
        cmd_off = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x1A, 0x05, 0x00, 0x00, 0xFD])
        s.send(cmd_off)
        time.sleep(0.5)
    
    s.close()

except Exception as e:
    print(f"Erreur: {e}")
