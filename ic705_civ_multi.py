#!/usr/bin/env python3
"""
Contrôle IC-705 via CI-V - Version améliorée
Lit plusieurs messages pour trouver la réponse à la commande
"""

import socket
import time

HOST = '127.0.0.1'  
PORT = 50002

print("="*60)
print("Contrôle IC-705 via CI-V (port 50002)")
print("="*60)
print(f"Connexion: {HOST}:{PORT}\n")

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((HOST, PORT))
    print("✅ Connecté au serveur CI-V\n")

    # Commande CI-V pour lire la fréquence
    cmd = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x03, 0xFD])
    #cmd = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x05, 0x00, 0x00, 0x00, 0x45, 0x01, 0xFD])
    
    print(f"→ Envoi: {cmd.hex(' ').upper()}")
    print("  (Read Operating Frequency)\n")
    s.send(cmd)
    
    print("Lecture des réponses...\n")
    
    # Lire jusqu'à 10 messages ou trouver la bonne réponse
    for attempt in range(10):
        response = bytearray()
        start = time.time()
        
        # Lire un message complet
        while time.time() - start < 2:
            byte = s.recv(1)
            if not byte:
                break
            response.extend(byte)
            if byte[0] == 0xFD:
                break
        
        if len(response) == 0:
            print("✗ Timeout - plus de messages")
            break
        
        print(f"Message {attempt+1}: {response.hex(' ').upper()}")
        print(f"  Longueur: {len(response)}, Commande: 0x{response[4]:02X}")
        
        # Vérifier si c'est la réponse à notre commande (0x03 ou 0x00/0x05)
        # Format: FE FE E0 A4 03 [5 bytes BCD] FD (11 bytes)
        # ou: FE FE E0 A4 00 [5 bytes BCD] FD (11 bytes) - certains radios
        if len(response) >= 11 and response[4] in [0x00, 0x03, 0x05]:
            # Les bytes 5-9 contiennent la fréquence en BCD
            freq_bytes = response[5:10]
            
            try:
                # Convertir BCD en fréquence (little-endian)
                freq_str = ''.join([f"{b:02x}" for b in reversed(freq_bytes)])
                freq_hz = int(freq_str)
                freq_mhz = freq_hz / 1_000_000
                
                print(f"\n{'='*60}")
                print("✅ FRÉQUENCE TROUVÉE !")
                print(f"{'='*60}")
                print(f"📻 Fréquence: {freq_mhz:.6f} MHz")
                print(f"📻 Fréquence: {freq_hz:,} Hz")
                print(f"{'='*60}")
                break
            except:
                pass
        
        print()
    
    s.close()

except Exception as e:
    print(f"❌ Erreur: {e}")

print("\n💡 Note: Le port CI-V renvoie de nombreux messages")
print("   asynchrones du radio. C'est normal !")
print("\n💡 Pour un usage simple, préférez ic705_final.py (rigctld)")
