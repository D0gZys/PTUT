# IC705 Python Library (sans WFview)

Cette lib fournit une implementation minimale du protocole UDP + CI-V de WFview
pour piloter un Icom IC-705 directement en Wi-Fi, sans dependance a WFview.

Elle est concue pour etre importee par une autre app (spectre/waterfall/CSV).

## Contenu rapide

- Connexion UDP controle (50001): handshake, login, token, demande de streams
- Connexion UDP CI-V (port renvoye par la radio, souvent 50002)
- Envoi/recep CI-V (FE FE ... FD)
- Lecture du flux Scope/Waterfall (commandes CI-V 0x27)

## Arborescence

- `ic705/__init__.py` : exports publics
- `ic705/client.py` : implementation complete
- `examples/ic705_full_example.py` : example complet (CSV RAW)

## Prerequis

- Python 3.8+
- IC-705 connecte en Wi-Fi (mode AP ou routeur)
- CI-V Remote active + identifiants OK
- Adresse CI-V du poste (ex: 0xA4)
- MAC du poste (ex: 00:90:C7:13:CA:75)
- Scope ON si tu veux le waterfall/spectre

## Installation / import

Depuis la racine `CodeSourceWfview`:

```bash
python -c "from ic705 import IC705Client; print(IC705Client)"
```

Si besoin, ajoute la racine au `PYTHONPATH`.

## Demarrage rapide

```python
from ic705 import IC705Client

client = IC705Client(
    radio_ip="192.168.59.1",
    username="IC-705-7",
    password="bouter20xx",
    radio_mac=bytes.fromhex("0090C713CA75"),
    radio_name="IC-705-7",
    civ_to=0xA4,
    civ_from=0xE0,
)

client.connect()
print("Freq:", client.get_frequency())
client.set_frequency(145500000)

payload = client.get_spectrum_frame(timeout_s=0.2)
if payload:
    # Utilise ton decodeur actuel
    decode_and_display(payload)

client.close()
```

## Exemple complet (CSV RAW)

Fichier: `examples/ic705_full_example.py`

Commande:

```bash
python examples/ic705_full_example.py --radio-ip 192.168.59.1 --username IC-705-7 --password bouter20xx --radio-mac 00:90:C7:13:CA:75 --radio-name IC-705-7 --civ-to 0xA4 --civ-from 0xE0 --get-freq --set-freq 145500000 --duration 10 --ref-level -77 --csv spectrum_raw.csv
```

### Format CSV (RAW)

Colonnes:

`timestamp,center_hz,ref_level_dbm,raw_0..raw_474`

- `timestamp` : HH:MM:SS.ffffff (UTC)
- `center_hz` : frequence centrale (Hz)
- `ref_level_dbm` : valeur REF stockee (pas de conversion)
- `raw_0..raw_474` : 475 points bruts, 0..160 (aucune conversion dBm)

Si tu veux seulement les RAW sans metadonnees, ajuste l’exemple.

## Architecture protocole (resume)

```
[Python] -> UDP controle (50001) -> login/token -> demande streams
                               -> status -> obtient civPort
[Python] -> UDP CI-V (civPort) -> CI-V encapsule (reply=0xC1)
```

### Handshake controle (50001)

Sequence type:

1) Envoi `control type=0x03` (Are you there)
2) Reception `0x04` (I am here) -> remoteId recupere
3) Envoi `0x06` (Are you ready)
4) Reception `0x06` -> login
5) Login -> token -> request stream -> status (civPort/audioPort)

### CI-V over UDP

Un paquet CI-V utilise un header UDP Icom (0x15) + payload CI-V:

```
FE FE <to> <from> <cmd> <data...> FD
```

Le flux CI-V est transporte avec:

- `reply=0xC1`
- `datalen` = taille CI-V
- `sendseq` interne (big-endian)
- `seq` externe (little-endian) pour le suivi

## Donnees Scope / Waterfall

Le scope est commande via CI-V `0x27`:

- `0x27 0x10` : Scope ON/OFF
- `0x27 0x11` : Scope Data Output ON/OFF
- `0x27 0x17` : Hold ON/OFF
- `0x27 0x00` : Wave Data (recu)

Structure attendue (LAN):

```
byte 0  : receiver
byte 1  : seq
byte 2  : seqMax
byte 3  : mode (0 center, 1 fixed, 2 scroll-c, 3 scroll-f)
byte 4-8: freq start (BCD LSB)
byte 9-13: freq end (BCD LSB)
byte 14 : oor (out of range)
byte 15.. : points RAW (475 bytes)
```

Sur LAN, on observe souvent `seq=1, seqMax=1` avec 475 points directs.

## API publique

### IC705Client(...)
Constructeur.

Parametres:
- `radio_ip`: IP de la radio (AP par defaut: 192.168.59.1)
- `username/password`: identifiants CI-V Remote
- `local_ip`: optionnel (auto detecte si None)
- `radio_name`: nom du poste (conninfo)
- `radio_mac`: bytes(6), recommande
- `radio_guid`: bytes(16) si pas de MAC
- `civ_to`: adresse CI-V du poste (ex: 0xA4)
- `civ_from`: adresse CI-V du PC (ex: 0xE0)
- `comp_name`: nom du client

### connect(timeout_s=20.0)
Ouvre les sockets, handshake controle, login/token, demande de stream,
ouvre le socket CI-V et lance le handshake CI-V.

Raises: `IC705Error` en cas d'echec.

### close()
Ferme toutes les sockets.

### send_civ_frame(civ_payload: bytes)
Envoie une trame CI-V brute (doit commencer par `FE FE` et finir par `FD`).

### send_civ_cmd(cmd: int, data: bytes = b"")
Construit automatiquement `FE FE <to> <from> <cmd> <data> FD`.

### get_frequency(timeout_s=1.0) -> Optional[int]
Envoie CI-V `0x03` (get freq). Retourne la frequence en Hz ou `None`.

### set_frequency(freq_hz: int)
Envoie CI-V `0x05` (set freq) avec BCD LSB.

### recv_civ(timeout_s=0.1) -> Optional[bytes]
Recoit une trame CI-V brute (payload) ou `None`.

### get_spectrum_frame(timeout_s=0.2) -> Optional[bytes]
Retourne un payload CI-V brut de type `0x27` (scope/waterfall).

### enable_scope_output(enable=True)
Active scope + output (0x27 0x10 + 0x27 0x11).

### set_scope_on(enable=True)
Allume/eteint le scope (0x27 0x10).

### set_scope_data_output(enable=True)
Active/desactive la sortie scope (0x27 0x11).

### set_scope_hold(hold=False)
Active/desactive le hold (0x27 0x17).

## Helpers internes

Fonctions exposees pour debug/integration:

- `passcode(s)`
- `pick_local_ip_for(...)`
- `reserve_two_udp_ports(...)`
- `compute_my_id(...)`
- `bcd_lsb_bytes_to_int(...)`
- `int_to_bcd_lsb_bytes(...)`
- `parse_civ_frame(payload)`

## Limitations actuelles

- Pas de retransmission UDP complete (comme WFview)
- Pas de stream audio
- Pas de gestion rigcaps complete
- Pas de parsing dBm integre (RAW uniquement)

## Depannage

Si le CSV reste vide:

- Scope ON sur le poste
- Scope Data Output active (la lib envoie 0x27/0x10 + 0x27/0x11)
- CI-V address correcte (ex: A4)
- MAC correcte (pas 00:00:00:00:00:00)
- Wi-Fi OK (AP ou routeur)

Erreurs frequentes:

- `Invalid Username/Password`: identifiants CI-V Remote incorrects
- `civRemotePort=0`: MAC/GUID refuse, token non accepte

## Notes

- Le format RAW est preserve pour permettre une calibration dBm ulterieure.
- Les points RAW sont 0..160 (plage IC-705 classique).
- Les donnees scope peuvent varier selon le mode (center/fixed/scroll).
