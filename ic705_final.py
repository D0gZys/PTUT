#!/usr/bin/env python3
"""
IC-705 Spectrum Display - Version Optimisée
============================================
Optimisations:
- Threading: réception et affichage séparés
- Buffer circulaire pré-alloué (zero-copy)
- Blitting matplotlib pour rafraîchissement rapide
- Socket non-bloquant avec select()
- Numpy vectorisé pour le traitement
- Gestion mémoire optimisée
"""

import socket
import select
import threading
import time
import numpy as np
import matplotlib
matplotlib.use('TkAgg')  # Backend optimisé
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.widgets import TextBox, Button
from matplotlib.colors import LinearSegmentedColormap
from collections import deque
from dataclasses import dataclass
from typing import Optional
import queue

# ============== CONFIGURATION ==============
@dataclass
class Config:
    """Configuration centralisée"""
    HOST: str = '127.0.0.1'
    PORT: int = 50002
    SPAN_KHZ: int = 50
    NUM_POINTS: int = 200
    WATERFALL_DEPTH: int = 150
    SOCKET_TIMEOUT: float = 0.1
    UPDATE_INTERVAL: int = 30  # ms entre mises à jour affichage
    FREQ_UPDATE_FRAMES: int = 10  # Demande de fréquence toutes les N trames
    RADIO_ADDR: int = 0xA4  # IC-705
    CTRL_ADDR: int = 0xE0

CONFIG = Config()

# ============== COLORMAP STYLE WFVIEW ==============
WFVIEW_COLORS = [
    (0.0, 0.0, 0.15),    # Bleu très foncé (bruit de fond)
    (0.0, 0.0, 0.4),     # Bleu foncé
    (0.0, 0.3, 0.7),     # Bleu
    (0.0, 0.6, 0.9),     # Bleu clair
    (0.0, 0.85, 1.0),    # Cyan
    (0.3, 1.0, 0.7),     # Cyan-vert
    (0.6, 1.0, 0.4),     # Vert-jaune
    (0.9, 1.0, 0.1),     # Jaune-vert
    (1.0, 0.9, 0.0),     # Jaune
    (1.0, 0.6, 0.0),     # Orange
    (1.0, 0.3, 0.0),     # Orange foncé
]
WFVIEW_CMAP = LinearSegmentedColormap.from_list('wfview', WFVIEW_COLORS, N=256)


# ============== PROTOCOLE CI-V ==============
class CIVProtocol:
    """Gestion optimisée du protocole CI-V"""
    
    __slots__ = ('radio_addr', 'ctrl_addr', '_buffer', '_freq_cache')
    
    def __init__(self, radio_addr: int = 0xA4, ctrl_addr: int = 0xE0):
        self.radio_addr = radio_addr
        self.ctrl_addr = ctrl_addr
        self._buffer = bytearray(4096)  # Buffer pré-alloué
        self._freq_cache = 0.0
    
    @staticmethod
    def decode_bcd_frequency(freq_bytes: bytes) -> float:
        """Décode BCD little-endian vers MHz (optimisé)"""
        freq = 0
        multiplier = 1
        for byte in freq_bytes:
            freq += (byte & 0x0F) * multiplier
            multiplier *= 10
            freq += ((byte >> 4) & 0x0F) * multiplier
            multiplier *= 10
        return freq / 1_000_000.0
    
    @staticmethod
    def encode_bcd_frequency(freq_mhz: float) -> bytes:
        """Encode MHz vers BCD little-endian (5 bytes)"""
        freq_hz = int(freq_mhz * 1_000_000)
        bcd = bytearray(5)
        for i in range(5):
            bcd[i] = (freq_hz % 10) | ((freq_hz // 10 % 10) << 4)
            freq_hz //= 100
        return bytes(bcd)
    
    def cmd_read_freq(self) -> bytes:
        """Commande lecture fréquence"""
        return bytes([0xFE, 0xFE, self.radio_addr, self.ctrl_addr, 0x03, 0xFD])
    
    def cmd_set_freq(self, freq_mhz: float) -> bytes:
        """Commande changement fréquence"""
        bcd = self.encode_bcd_frequency(freq_mhz)
        return bytes([0xFE, 0xFE, self.radio_addr, self.ctrl_addr, 0x05]) + bcd + bytes([0xFD])
    
    def cmd_streaming_on(self) -> bytes:
        """Commande activation streaming"""
        return bytes([0xFE, 0xFE, self.radio_addr, self.ctrl_addr, 0x1A, 0x05, 0x00, 0x01, 0xFD])
    
    def cmd_streaming_off(self) -> bytes:
        """Commande désactivation streaming"""
        return bytes([0xFE, 0xFE, self.radio_addr, self.ctrl_addr, 0x1A, 0x05, 0x00, 0x00, 0xFD])


# ============== RÉCEPTEUR CI-V (THREAD) ==============
class CIVReceiver(threading.Thread):
    """Thread de réception des données CI-V"""
    
    def __init__(self, sock: socket.socket, spectrum_queue: queue.Queue, 
                 freq_callback, config: Config):
        super().__init__(daemon=True)
        self.sock = sock
        self.spectrum_queue = spectrum_queue
        self.freq_callback = freq_callback
        self.config = config
        self.protocol = CIVProtocol(config.RADIO_ADDR, config.CTRL_ADDR)
        self.running = True
        self._buffer = bytearray()
        self._frame_count = 0
        
        # Buffer numpy pré-alloué pour les données de spectre
        self._spectrum_buffer = np.zeros(config.NUM_POINTS, dtype=np.float32)
        # Indices pré-calculés pour le sous-échantillonnage
        self._resample_indices = None
    
    def stop(self):
        """Arrête le thread"""
        self.running = False
    
    def _parse_messages(self):
        """Parse les messages CI-V du buffer (optimisé)"""
        messages = []
        
        while True:
            # Chercher le début d'un message
            try:
                start = self._buffer.index(0xFE)
                if start > 0:
                    del self._buffer[:start]
                    start = 0
            except ValueError:
                self._buffer.clear()
                break
            
            # Vérifier qu'on a FE FE
            if len(self._buffer) < 2:
                break
            if self._buffer[1] != 0xFE:
                del self._buffer[:1]
                continue
            
            # Chercher la fin du message
            try:
                end = self._buffer.index(0xFD, 2) + 1
                messages.append(bytes(self._buffer[:end]))
                del self._buffer[:end]
            except ValueError:
                # Message incomplet
                if len(self._buffer) > 1000:
                    # Buffer trop grand, nettoyer
                    self._buffer.clear()
                break
        
        return messages
    
    def _extract_spectrum_data(self, msg: bytes) -> Optional[np.ndarray]:
        """Extrait les données de spectre (optimisé numpy)"""
        if len(msg) < 50:
            return None
        
        # Données d'amplitude à partir du byte 19
        amp_start = 19
        amp_end = len(msg) - 1  # Exclure FD
        raw_len = amp_end - amp_start
        
        if raw_len < 10:
            return None
        
        # Créer un array numpy directement depuis les bytes
        raw_data = np.frombuffer(msg[amp_start:amp_end], dtype=np.uint8).astype(np.float32)
        
        # Sous-échantillonnage optimisé
        if raw_len >= self.config.NUM_POINTS:
            # Calculer les indices une seule fois si la taille est constante
            if self._resample_indices is None or len(self._resample_indices) != self.config.NUM_POINTS:
                self._resample_indices = np.linspace(0, raw_len - 1, 
                                                      self.config.NUM_POINTS, dtype=np.int32)
            np.take(raw_data, self._resample_indices, out=self._spectrum_buffer)
            return self._spectrum_buffer.copy()
        else:
            result = np.zeros(self.config.NUM_POINTS, dtype=np.float32)
            result[:raw_len] = raw_data
            return result
    
    def run(self):
        """Boucle principale de réception"""
        self.sock.setblocking(False)
        
        while self.running:
            # Utiliser select pour attendre les données (non-bloquant)
            ready, _, _ = select.select([self.sock], [], [], 0.05)
            
            if not ready:
                continue
            
            try:
                data = self.sock.recv(4096)
                if not data:
                    continue
                self._buffer.extend(data)
            except (socket.error, BlockingIOError):
                continue
            
            # Parser les messages
            messages = self._parse_messages()
            
            for msg in messages:
                if len(msg) < 5:
                    continue
                
                cmd = msg[4]
                
                # Message de fréquence
                if cmd == 0x03 and len(msg) == 11:
                    freq = self.protocol.decode_bcd_frequency(msg[5:10])
                    if freq > 0:
                        self.freq_callback(freq)
                
                # Message de spectre
                elif cmd == 0x27 and len(msg) > 100:
                    spectrum = self._extract_spectrum_data(msg)
                    if spectrum is not None:
                        # Ne pas bloquer si la queue est pleine
                        try:
                            self.spectrum_queue.put_nowait(spectrum)
                        except queue.Full:
                            # Retirer l'ancien et mettre le nouveau
                            try:
                                self.spectrum_queue.get_nowait()
                                self.spectrum_queue.put_nowait(spectrum)
                            except queue.Empty:
                                pass
                        
                        self._frame_count += 1


# ============== AFFICHAGE OPTIMISÉ ==============
class SpectrumDisplay:
    """Affichage optimisé avec blitting"""
    
    def __init__(self, config: Config):
        self.config = config
        self.center_freq_mhz = 145.000
        self._last_freq = 145.000
        
        # Données pré-allouées
        self.freq_axis = np.linspace(
            self.center_freq_mhz - config.SPAN_KHZ/2000,
            self.center_freq_mhz + config.SPAN_KHZ/2000,
            config.NUM_POINTS
        )
        self.spectrum_data = np.zeros(config.NUM_POINTS, dtype=np.float32)
        
        # Waterfall pré-alloué (contiguous memory)
        self.waterfall_data = np.zeros((config.WATERFALL_DEPTH, config.NUM_POINTS), 
                                        dtype=np.float32, order='C')
        self._waterfall_idx = 0
        
        # Créer la figure
        self._setup_figure()
        
        # Variables pour le blitting
        self._background = None
        self._needs_full_redraw = True
    
    def _setup_figure(self):
        """Configure la figure matplotlib"""
        plt.style.use('dark_background')
        
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(12, 7))
        self.fig.patch.set_facecolor('#0a0a0a')
        
        # === Spectre ===
        self.line, = self.ax1.plot(self.freq_axis, self.spectrum_data, 
                                    color='#FFFF00', linewidth=1)
        # Ligne verticale pour la fréquence centrale
        self.center_line = self.ax1.axvline(x=self.center_freq_mhz, color="#44FF0095", 
                                             linewidth=1.5, linestyle='--', alpha=0.8)
        self.ax1.set_xlim(self.freq_axis[0], self.freq_axis[-1])
        self.ax1.set_ylim(0, 160)
        self.ax1.set_xlabel('Fréquence (MHz)', fontsize=10)
        self.ax1.set_ylabel('Amplitude', fontsize=10)
        self.ax1.set_title(f'Spectre IC-705 - {self.center_freq_mhz:.6f} MHz', fontsize=11)
        self.ax1.grid(True, alpha=0.3, color='#444444')
        self.ax1.set_facecolor('#000022')
        self.ax1.ticklabel_format(useOffset=False, style='plain')
        self.ax1.xaxis.set_major_formatter(ticker.FormatStrFormatter('%.3f'))
        
        # === Waterfall ===
        self.waterfall_img = self.ax2.imshow(
            self.waterfall_data, 
            aspect='auto', 
            cmap=WFVIEW_CMAP,
            extent=[self.freq_axis[0], self.freq_axis[-1], self.config.WATERFALL_DEPTH, 0],
            vmin=0, vmax=200,
            interpolation='bilinear',
            origin='upper'
        )
        self.ax2.set_xlabel('Fréquence (MHz)', fontsize=10)
        self.ax2.set_ylabel('Temps', fontsize=10)
        self.ax2.set_title('Waterfall', fontsize=11)
        self.ax2.ticklabel_format(useOffset=False, style='plain')
        self.ax2.xaxis.set_major_formatter(ticker.FormatStrFormatter('%.3f'))
        
        # Colorbar
        self.cbar = plt.colorbar(self.waterfall_img, ax=self.ax2, label='Amplitude')
        
        # === Contrôles ===
        plt.subplots_adjust(bottom=0.15)
        
        # Zone de texte fréquence - Style sombre
        freq_box_ax = plt.axes([0.15, 0.02, 0.2, 0.04])
        freq_box_ax.set_facecolor('#1a1a2e')
        self.freq_textbox = TextBox(freq_box_ax, 'Freq (MHz): ', 
                                     initial=f'{self.center_freq_mhz:.6f}',
                                     color='#1a1a2e',        # Fond de la zone de texte
                                     hovercolor='#2a2a4e')   # Fond au survol
        # Personnaliser les couleurs du texte
        self.freq_textbox.text_disp.set_color('#00ff00')  # Texte vert
        self.freq_textbox.label.set_color('#aaaaaa')       # Label gris clair
        
        # Bouton appliquer - Style sombre
        btn_ax = plt.axes([0.4, 0.02, 0.1, 0.04])
        self.btn_apply = Button(btn_ax, 'Appliquer', 
                                color='#2a2a4e',           # Fond du bouton
                                hovercolor='#4a4a6e')      # Fond au survol
        self.btn_apply.label.set_color('#ffffff')          # Texte blanc
        
        # Callback pour la fréquence
        self.pending_freq = None
        self.freq_textbox.on_submit(self._on_freq_submit)
        self.btn_apply.on_clicked(self._on_apply_click)
        
        plt.tight_layout(rect=[0, 0.08, 1, 1])
    
    def _on_freq_submit(self, text):
        """Callback soumission fréquence"""
        try:
            freq = float(text)
            if 0.1 < freq < 500:
                self.pending_freq = freq
        except ValueError:
            pass
    
    def _on_apply_click(self, event):
        """Callback bouton appliquer"""
        self._on_freq_submit(self.freq_textbox.text)
    
    def update_frequency(self, freq_mhz: float):
        """Met à jour la fréquence centrale"""
        self.center_freq_mhz = freq_mhz
    
    def update_display(self, spectrum: np.ndarray) -> bool:
        """Met à jour l'affichage avec les nouvelles données"""
        if not plt.fignum_exists(self.fig.number):
            return False
        
        # Mettre à jour les données du spectre
        self.spectrum_data[:] = spectrum
        
        # Mettre à jour le waterfall (scroll optimisé)
        # Déplacer les lignes vers le bas et ajouter la nouvelle en haut
        self.waterfall_data[1:] = self.waterfall_data[:-1]
        self.waterfall_data[0] = spectrum
        
        # Vérifier si la fréquence a changé
        if abs(self.center_freq_mhz - self._last_freq) > 0.0001:
            self._last_freq = self.center_freq_mhz
            self._update_freq_axis()
            self._needs_full_redraw = True
        
        # Mise à jour graphique
        self.line.set_ydata(self.spectrum_data)
        self.waterfall_img.set_data(self.waterfall_data)
        
        # Redraw complet pour éviter les artefacts de superposition
        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()
        return True
    
    def _update_freq_axis(self):
        """Met à jour l'axe des fréquences"""
        self.freq_axis = np.linspace(
            self.center_freq_mhz - self.config.SPAN_KHZ/2000,
            self.center_freq_mhz + self.config.SPAN_KHZ/2000,
            self.config.NUM_POINTS
        )
        
        self.line.set_xdata(self.freq_axis)
        self.center_line.set_xdata([self.center_freq_mhz, self.center_freq_mhz])  # Mise à jour ligne centrale
        self.ax1.set_xlim(self.freq_axis[0], self.freq_axis[-1])
        self.ax1.set_title(f'Spectre IC-705 - {self.center_freq_mhz:.6f} MHz')
        
        self.waterfall_img.set_extent([
            self.freq_axis[0], self.freq_axis[-1], 
            self.config.WATERFALL_DEPTH, 0
        ])
        self.ax2.set_xlim(self.freq_axis[0], self.freq_axis[-1])
        
        # Mettre à jour la zone de texte
        self.freq_textbox.set_val(f'{self.center_freq_mhz:.6f}')
    
    def show(self):
        """Affiche la figure"""
        plt.ion()
        plt.show(block=False)
    
    def is_open(self) -> bool:
        """Vérifie si la fenêtre est ouverte"""
        return plt.fignum_exists(self.fig.number)
    
    def close(self):
        """Ferme la figure"""
        plt.close(self.fig)


# ============== APPLICATION PRINCIPALE ==============
class IC705SpectrumApp:
    """Application principale"""
    
    def __init__(self, config: Config = CONFIG):
        self.config = config
        self.protocol = CIVProtocol(config.RADIO_ADDR, config.CTRL_ADDR)
        self.sock = None
        self.receiver = None
        self.display = None
        self.spectrum_queue = queue.Queue(maxsize=5)
        self._running = False
        self._freq_lock = threading.Lock()
        self._current_freq = 145.000
    
    def _freq_callback(self, freq: float):
        """Callback appelé quand une fréquence est reçue"""
        with self._freq_lock:
            self._current_freq = freq
    
    def connect(self) -> bool:
        """Connexion au serveur CI-V"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(2)
            self.sock.connect((self.config.HOST, self.config.PORT))
            print(f"✅ Connecté à {self.config.HOST}:{self.config.PORT}")
            return True
        except Exception as e:
            print(f"❌ Erreur connexion: {e}")
            return False
    
    def get_initial_frequency(self):
        """Récupère la fréquence initiale"""
        self.sock.settimeout(0.5)
        self.sock.send(self.protocol.cmd_read_freq())
        
        # Lire quelques messages
        buffer = bytearray()
        for _ in range(10):
            try:
                data = self.sock.recv(256)
                buffer.extend(data)
                
                # Chercher une réponse de fréquence
                for i in range(len(buffer) - 10):
                    if (buffer[i] == 0xFE and buffer[i+1] == 0xFE and 
                        buffer[i+4] == 0x03 and buffer[i+10] == 0xFD):
                        freq = self.protocol.decode_bcd_frequency(buffer[i+5:i+10])
                        if freq > 0:
                            self._current_freq = freq
                            print(f"✅ Fréquence initiale: {freq:.6f} MHz")
                            return freq
            except socket.timeout:
                break
        
        print(f"ℹ️  Fréquence par défaut: {self._current_freq:.6f} MHz")
        return self._current_freq
    
    def start_streaming(self):
        """Active le streaming spectral"""
        self.sock.send(self.protocol.cmd_streaming_on())
        print("✅ Streaming spectral activé")
    
    def stop_streaming(self):
        """Désactive le streaming spectral"""
        try:
            self.sock.send(self.protocol.cmd_streaming_off())
        except:
            pass
    
    def run(self):
        """Boucle principale de l'application"""
        print("=" * 60)
        print("IC-705 Spectrum Display - Version Optimisée")
        print("=" * 60)
        
        try:
            # Connexion
            if not self.connect():
                return
            
            # Fréquence initiale
            self.get_initial_frequency()
            
            # Activer streaming
            self.start_streaming()
            
            # Créer l'affichage
            self.display = SpectrumDisplay(self.config)
            self.display.update_frequency(self._current_freq)
            self.display.show()
            
            # Démarrer le thread de réception
            self.receiver = CIVReceiver(
                self.sock, 
                self.spectrum_queue, 
                self._freq_callback,
                self.config
            )
            self.receiver.start()
            
            print("\n🎯 Affichage en temps réel... (Fermez la fenêtre pour arrêter)")
            print()
            
            self._running = True
            frame_count = 0
            last_time = time.time()
            
            # Boucle d'affichage
            while self._running and self.display.is_open():
                # Vérifier si une nouvelle fréquence doit être envoyée
                if self.display.pending_freq is not None:
                    freq = self.display.pending_freq
                    self.display.pending_freq = None
                    self.sock.send(self.protocol.cmd_set_freq(freq))
                    with self._freq_lock:
                        self._current_freq = freq
                    print(f"→ Fréquence changée: {freq:.6f} MHz")
                
                # Demander la fréquence périodiquement
                if frame_count % self.config.FREQ_UPDATE_FRAMES == 0:
                    try:
                        self.sock.send(self.protocol.cmd_read_freq())
                    except:
                        pass
                
                # Récupérer et afficher les données de spectre
                try:
                    spectrum = self.spectrum_queue.get(timeout=0.1)
                    
                    # Mettre à jour la fréquence
                    with self._freq_lock:
                        self.display.update_frequency(self._current_freq)
                    
                    # Mettre à jour l'affichage
                    if not self.display.update_display(spectrum):
                        break
                    
                    frame_count += 1
                    
                    # Stats toutes les 100 trames
                    if frame_count % 100 == 0:
                        now = time.time()
                        fps = 100 / (now - last_time)
                        print(f"  {frame_count} trames | {fps:.1f} FPS")
                        last_time = now
                        
                except queue.Empty:
                    # Pas de données, juste traiter les événements
                    self.display.fig.canvas.flush_events()
            
            print("\n✅ Fenêtre fermée")
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Interruption utilisateur")
        
        except Exception as e:
            print(f"\n❌ Erreur: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Nettoyage des ressources"""
        self._running = False
        
        # Arrêter le récepteur
        if self.receiver:
            self.receiver.stop()
            self.receiver.join(timeout=1)
        
        # Désactiver streaming et fermer socket
        if self.sock:
            try:
                self.stop_streaming()
                time.sleep(0.1)
                self.sock.close()
                print("✅ Connexion fermée")
            except:
                pass
        
        # Fermer l'affichage
        if self.display:
            self.display.close()


# ============== POINT D'ENTRÉE ==============
if __name__ == '__main__':
    app = IC705SpectrumApp()
    app.run()
