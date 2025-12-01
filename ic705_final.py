#!/usr/bin/env python3
"""
Contrôle IC-705 via wfview - Version fonctionnelle
Utilise rigctld (port 4532) qui fonctionne correctement
"""

import socket

# Configuration
HOST = '127.0.0.1'
PORT = 4532  # Port rigctld (Hamlib)

print("="*60)
print("Contrôle IC-705 via wfview (rigctld)")
print("="*60)
print(f"Connexion: {HOST}:{PORT}\n")

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    s.connect((HOST, PORT))
    print("✅ Connecté à rigctld (wfview)\n")

    # Commande pour lire la fréquence
    cmd = "f\n"
    print("→ Commande: get frequency")
    s.send(cmd.encode())
    
    # Lire la réponse
    data = s.recv(1024)
    s.close()

    if data:
        response = data.decode().strip()
        print(f"← Réponse: {response}\n")
        
        try:
            freq_hz = float(response)
            freq_mhz = freq_hz / 1_000_000
            
            print("="*60)
            print("✅ SUCCÈS")
            print("="*60)
            print(f"📻 Fréquence: {freq_mhz:.6f} MHz")
            print(f"📻 Fréquence: {int(freq_hz):,} Hz")
            print("="*60)
            
            print(f"\n💡 Commande CI-V équivalente:")
            print(f"   FE FE A4 E0 03 FD")
            print(f"   (Read Operating Frequency)")
            
        except ValueError:
            print(f"⚠ Format inattendu: {response}")
    else:
        print("✗ Aucune réponse reçue")

except Exception as e:
    print(f"❌ Erreur: {e}")
    print("\nVérifiez que:")
    print("  1. wfview est lancé")
    print("  2. wfview est connecté à l'IC-705")
    print("  3. RigCtld est activé dans External Control")
