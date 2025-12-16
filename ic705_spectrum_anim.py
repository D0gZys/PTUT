#!/usr/bin/env python3
"""
IC-705 Spectrum Display - Version FuncAnimation
Animation fluide avec matplotlib.animation.FuncAnimation
"""

import socket
import time
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.animation import FuncAnimation
from matplotlib.widgets import TextBox, Button
from matplotlib.colors import LinearSegmentedColormap
from collections import deque

# ============== COLORMAP STYLE WFVIEW ==============
wfview_colors = [
    (0.0, 0.0, 0.2),      # Bleu très foncé (bruit)
    (0.0, 0.0, 0.5),      # Bleu foncé
    (0.0, 0.2, 0.8),      # Bleu
    (0.0, 0.5, 1.0),      # Bleu clair
    (0.0, 0.8, 1.0),      # Cyan
    (0.2, 1.0, 0.8),      # Cyan-vert
    (0.5, 1.0, 0.5),      # Vert clair
    (0.8, 1.0, 0.2),      # Jaune-vert
    (1.0, 1.0, 0.0),      # Jaune
    (1.0, 0.8, 0.0),      # Orange
    (1.0, 0.5, 0.0),      # Orange foncé
]
wfview_cmap = LinearSegmentedColormap.from_list('wfview', wfview_colors, N=256)

# ============== CONFIGURATION ==============
HOST = '127.0.0.1'
PORT = 50002
SPAN_KHZ = 50
NUM_POINTS = 200
WATERFALL_DEPTH = 150
ANIMATION_INTERVAL = 30  # ms entre chaque frame

# ============== CLASSE PRINCIPALE ==============
class IC705SpectrumDisplay:
    """Affichage du spectre IC-705 avec FuncAnimation"""
    
    def __init__(self):
        self.sock = None
        self.center_freq_mhz = 145.000
        self.last_freq = 145.000
        self.waterfall_data = np.zeros((WATERFALL_DEPTH, NUM_POINTS))
        self.spectrum_data = np.zeros(NUM_POINTS)
        self.new_freq_to_set = None
        self.frame_count = 0
        self.running = True
        
        # Buffer pour les messages
        self.msg_buffer = bytearray()
        
    def connect(self):
        """Connexion au serveur CI-V"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(0.1)  # Timeout court pour non-blocage
        self.sock.connect((HOST, PORT))
        print(f"✅ Connecté à {HOST}:{PORT}")
        
    def decode_bcd_frequency(self, freq_bytes):
        """Décode la fréquence BCD little-endian"""
        try:
            freq = 0
            multiplier = 1
            for byte in freq_bytes:
                freq += (byte & 0x0F) * multiplier
                multiplier *= 10
                freq += ((byte >> 4) & 0x0F) * multiplier
                multiplier *= 10
            return freq / 1_000_000.0
        except:
            return None
    
    def encode_bcd_frequency(self, freq_mhz):
        """Encode une fréquence en BCD little-endian"""
        freq_hz = int(freq_mhz * 1_000_000)
        bcd = bytearray(5)
        for i in range(5):
            bcd[i] = (freq_hz % 10) | ((freq_hz // 10 % 10) << 4)
            freq_hz //= 100
        return bytes(bcd)
    
    def get_initial_frequency(self):
        """Récupère la fréquence initiale"""
        cmd = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x03, 0xFD])
        self.sock.send(cmd)
        time.sleep(0.2)
        
        try:
            data = self.sock.recv(1024)
            # Chercher une réponse de fréquence
            for i in range(len(data) - 10):
                if data[i] == 0xFE and data[i+1] == 0xFE and data[i+4] == 0x03:
                    freq = self.decode_bcd_frequency(data[i+5:i+10])
                    if freq and freq > 0:
                        self.center_freq_mhz = freq
                        self.last_freq = freq
                        return freq
        except:
            pass
        return self.center_freq_mhz
    
    def start_streaming(self):
        """Active le streaming spectral"""
        cmd = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x1A, 0x05, 0x00, 0x01, 0xFD])
        self.sock.send(cmd)
        print("Streaming spectral activé")
    
    def stop_streaming(self):
        """Désactive le streaming spectral"""
        try:
            cmd = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x1A, 0x05, 0x00, 0x00, 0xFD])
            self.sock.send(cmd)
        except:
            pass
    
    def set_frequency(self, freq_mhz):
        """Change la fréquence de l'IC-705"""
        try:
            bcd = self.encode_bcd_frequency(freq_mhz)
            cmd = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x05]) + bcd + bytes([0xFD])
            self.sock.send(cmd)
            self.center_freq_mhz = freq_mhz
            print(f"→ Fréquence: {freq_mhz:.6f} MHz")
            return True
        except Exception as e:
            print(f"Erreur: {e}")
            return False
    
    def request_frequency(self):
        """Demande la fréquence actuelle"""
        try:
            cmd = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x03, 0xFD])
            self.sock.send(cmd)
        except:
            pass
    
    def read_and_parse_data(self):
        """Lit les données socket et parse les messages CI-V"""
        try:
            data = self.sock.recv(4096)
            if data:
                self.msg_buffer.extend(data)
        except socket.timeout:
            pass
        except:
            return None, None
        
        spectrum = None
        freq = None
        
        # Parser les messages dans le buffer
        while len(self.msg_buffer) >= 6:
            # Chercher le début d'un message
            try:
                start = self.msg_buffer.index(0xFE)
                if start > 0:
                    del self.msg_buffer[:start]
            except ValueError:
                self.msg_buffer.clear()
                break
            
            if len(self.msg_buffer) < 2 or self.msg_buffer[1] != 0xFE:
                del self.msg_buffer[:1]
                continue
            
            # Chercher la fin
            try:
                end = self.msg_buffer.index(0xFD, 2) + 1
            except ValueError:
                break  # Message incomplet
            
            # Extraire le message
            msg = bytes(self.msg_buffer[:end])
            del self.msg_buffer[:end]
            
            if len(msg) < 5:
                continue
            
            cmd = msg[4]
            
            # Message de fréquence
            if cmd == 0x03 and len(msg) == 11:
                f = self.decode_bcd_frequency(msg[5:10])
                if f and f > 0:
                    freq = f
                    self.center_freq_mhz = f
            
            # Message de spectre
            elif cmd == 0x27 and len(msg) > 50:
                amp_data = msg[19:-1]
                if len(amp_data) >= 10:
                    raw_len = len(amp_data)
                    if raw_len >= NUM_POINTS:
                        indices = np.linspace(0, raw_len - 1, NUM_POINTS, dtype=int)
                        spectrum = np.array([amp_data[i] for i in indices], dtype=np.float32)
                    else:
                        spectrum = np.zeros(NUM_POINTS, dtype=np.float32)
                        spectrum[:raw_len] = list(amp_data)
        
        # Limiter la taille du buffer
        if len(self.msg_buffer) > 10000:
            self.msg_buffer.clear()
        
        return spectrum, freq
    
    def setup_figure(self):
        """Configure la figure matplotlib"""
        plt.style.use('dark_background')
        
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(12, 7))
        self.fig.patch.set_facecolor('#0a0a0a')
        
        # Axe des fréquences
        self.freq_axis = np.linspace(
            self.center_freq_mhz - SPAN_KHZ/2000,
            self.center_freq_mhz + SPAN_KHZ/2000,
            NUM_POINTS
        )
        
        # === Spectre ===
        self.line, = self.ax1.plot(self.freq_axis, self.spectrum_data, 
                                    color='#FFFF00', linewidth=1)
        self.center_line = self.ax1.axvline(x=self.center_freq_mhz, color='#FF0000',
                                             linewidth=1.5, linestyle='--', alpha=0.7)
        self.ax1.set_xlim(self.freq_axis[0], self.freq_axis[-1])
        self.ax1.set_ylim(0, 160)
        self.ax1.set_xlabel('Fréquence (MHz)')
        self.ax1.set_ylabel('Amplitude')
        self.ax1.set_title(f'Spectre IC-705 - {self.center_freq_mhz:.6f} MHz')
        self.ax1.grid(True, alpha=0.3, color='#444444')
        self.ax1.set_facecolor('#000022')
        self.ax1.ticklabel_format(useOffset=False, style='plain')
        self.ax1.xaxis.set_major_formatter(ticker.FormatStrFormatter('%.3f'))
        
        # === Waterfall ===
        self.waterfall_img = self.ax2.imshow(
            self.waterfall_data, aspect='auto', cmap=wfview_cmap,
            extent=[self.freq_axis[0], self.freq_axis[-1], WATERFALL_DEPTH, 0],
            vmin=0, vmax=200, interpolation='bilinear', origin='upper'
        )
        self.ax2.set_xlabel('Fréquence (MHz)')
        self.ax2.set_ylabel('Temps')
        self.ax2.set_title('Waterfall')
        self.ax2.ticklabel_format(useOffset=False, style='plain')
        self.ax2.xaxis.set_major_formatter(ticker.FormatStrFormatter('%.3f'))
        plt.colorbar(self.waterfall_img, ax=self.ax2, label='Amplitude')
        
        # === Contrôles ===
        plt.subplots_adjust(bottom=0.15)
        
        # Zone de texte
        freq_box_ax = plt.axes([0.15, 0.02, 0.2, 0.04])
        freq_box_ax.set_facecolor('#1a1a2e')
        self.freq_textbox = TextBox(freq_box_ax, 'Freq (MHz): ',
                                     initial=f'{self.center_freq_mhz:.6f}',
                                     color='#1a1a2e', hovercolor='#2a2a4e')
        self.freq_textbox.text_disp.set_color('#00ff00')
        self.freq_textbox.label.set_color('#aaaaaa')
        self.freq_textbox.on_submit(self._on_freq_submit)
        
        # Bouton
        btn_ax = plt.axes([0.4, 0.02, 0.1, 0.04])
        self.btn_apply = Button(btn_ax, 'Appliquer', color='#2a2a4e', hovercolor='#4a4a6e')
        self.btn_apply.label.set_color('#ffffff')
        self.btn_apply.on_clicked(self._on_apply_click)
        
        plt.tight_layout(rect=[0, 0.08, 1, 1])
    
    def _on_freq_submit(self, text):
        try:
            freq = float(text)
            if 0.1 < freq < 500:
                self.new_freq_to_set = freq
        except:
            pass
    
    def _on_apply_click(self, event):
        self._on_freq_submit(self.freq_textbox.text)
    
    def update_freq_axis(self):
        """Met à jour l'axe des fréquences"""
        self.freq_axis = np.linspace(
            self.center_freq_mhz - SPAN_KHZ/2000,
            self.center_freq_mhz + SPAN_KHZ/2000,
            NUM_POINTS
        )
        self.line.set_xdata(self.freq_axis)
        self.center_line.set_xdata([self.center_freq_mhz])
        self.ax1.set_xlim(self.freq_axis[0], self.freq_axis[-1])
        self.ax1.set_title(f'Spectre IC-705 - {self.center_freq_mhz:.6f} MHz')
        self.waterfall_img.set_extent([self.freq_axis[0], self.freq_axis[-1], WATERFALL_DEPTH, 0])
        self.ax2.set_xlim(self.freq_axis[0], self.freq_axis[-1])
        self.freq_textbox.set_val(f'{self.center_freq_mhz:.6f}')
    
    def animate(self, frame):
        """Fonction d'animation appelée par FuncAnimation"""
        if not self.running:
            return self.line, self.waterfall_img
        
        # Appliquer nouvelle fréquence si demandée
        if self.new_freq_to_set is not None:
            self.set_frequency(self.new_freq_to_set)
            self.new_freq_to_set = None
        
        # Demander la fréquence périodiquement
        if self.frame_count % 10 == 0:
            self.request_frequency()
        
        # Lire et parser les données
        spectrum, freq = self.read_and_parse_data()
        
        # Mettre à jour si nouvelles données
        if spectrum is not None:
            self.spectrum_data = spectrum
            
            # Scroll waterfall
            self.waterfall_data[1:] = self.waterfall_data[:-1]
            self.waterfall_data[0] = spectrum
            
            # Mettre à jour l'axe si fréquence changée
            if abs(self.center_freq_mhz - self.last_freq) > 0.0001:
                self.last_freq = self.center_freq_mhz
                self.update_freq_axis()
            
            # Mettre à jour les graphiques
            self.line.set_ydata(self.spectrum_data)
            self.waterfall_img.set_data(self.waterfall_data)
            
            self.frame_count += 1
            if self.frame_count % 100 == 0:
                print(f"  {self.frame_count} trames...")
        
        return self.line, self.waterfall_img
    
    def run(self):
        """Lance l'application"""
        print("=" * 60)
        print("IC-705 Spectrum Display - FuncAnimation")
        print("=" * 60)
        
        try:
            # Connexion
            self.connect()
            
            # Fréquence initiale
            print("→ Récupération de la fréquence...")
            self.get_initial_frequency()
            print(f"Fréquence: {self.center_freq_mhz:.6f} MHz")
            
            # Streaming
            self.start_streaming()
            
            # Figure
            self.setup_figure()
            
            print("\nAffichage en temps réel)\n")
            
            # Animation avec FuncAnimation
            self.anim = FuncAnimation(
                self.fig,
                self.animate,
                interval=ANIMATION_INTERVAL,
                blit=False,  # blit=False pour mise à jour complète
                cache_frame_data=False
            )
            
            plt.show()
            
        except KeyboardInterrupt:
            print("\n\nInterruption utilisateur")
        except Exception as e:
            print(f"Erreur: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Nettoyage"""
        self.running = False
        if self.sock:
            try:
                self.stop_streaming()
                time.sleep(0.1)
                self.sock.close()
                print("Connexion fermée")
            except:
                pass
        plt.close('all')


# ============== POINT D'ENTRÉE ==============
if __name__ == '__main__':
    app = IC705SpectrumDisplay()
    app.run()
