# Extraits “copier/coller” depuis WFview (IC-705 Wi‑Fi / UDP / CI‑V)

Ce fichier contient uniquement des extraits **verbatim** du code source WFview, dans l’ordre demandé.

## 1) `passcode()` + table `sequence[]` (obligatoire)

Source: `include/icomudpbase.h` (fonction `static inline void passcode(QString in, QByteArray& out)`).

Note: dans ce dépôt, `sequence[]` est déclarée sans taille explicite, et l’initialiseur contient **159** entrées (pas 256).

```cpp
static inline void passcode(QString in, QByteArray& out)
{
	const quint8 sequence[] =
	{
		0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
		0x47,0x5d,0x4c,0x42,0x66,0x20,0x23,0x46,0x4e,0x57,0x45,0x3d,0x67,0x76,0x60,0x41,0x62,0x39,0x59,0x2d,0x68,0x7e,
		0x7c,0x65,0x7d,0x49,0x29,0x72,0x73,0x78,0x21,0x6e,0x5a,0x5e,0x4a,0x3e,0x71,0x2c,0x2a,0x54,0x3c,0x3a,0x63,0x4f,
		0x43,0x75,0x27,0x79,0x5b,0x35,0x70,0x48,0x6b,0x56,0x6f,0x34,0x32,0x6c,0x30,0x61,0x6d,0x7b,0x2f,0x4b,0x64,0x38,
		0x2b,0x2e,0x50,0x40,0x3f,0x55,0x33,0x37,0x25,0x77,0x24,0x26,0x74,0x6a,0x28,0x53,0x4d,0x69,0x22,0x5c,0x44,0x31,
		0x36,0x58,0x3b,0x7a,0x51,0x5f,0x52,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0

	};

	QByteArray ba = in.toLocal8Bit();
	uchar* ascii = (uchar*)ba.constData();
	for (int i = 0; i < in.length() && i < 16; i++)
	{
		int p = ascii[i] + i;
		if (p > 126)
		{
			p = 32 + p % 127;
		}
		out.append(sequence[p]);
	}
	return;
}
```

## 2) Définitions C des structs packés (obligatoire)

Source: `include/packettypes.h`.

### 2.1 Tailles / constantes

```cpp
// Various settings used by both client and server
#define PURGE_SECONDS 10
#define TOKEN_RENEWAL 60000
#define PING_PERIOD 500
#define IDLE_PERIOD 100
#define AREYOUTHERE_PERIOD 500
#define WATCHDOG_PERIOD 500             
#define RETRANSMIT_PERIOD 100           // How often to attempt retransmit
#define LOCK_PERIOD 10                  // How long to try to lock mutex (ms)
#define STALE_CONNECTION 15             // Not heard from in this many seconds
#define BUFSIZE 500 // Number of packets to buffer
#define MAX_MISSING 50 // More than this indicates serious network problem 
#define AUDIO_PERIOD 20 
#define GUIDLEN 16


// Fixed Size Packets
#define CONTROL_SIZE            0x10
#define WATCHDOG_SIZE           0x14
#define PING_SIZE               0x15
#define OPENCLOSE_SIZE          0x16
#define RETRANSMIT_RANGE_SIZE   0x18
#define TOKEN_SIZE              0x40
#define STATUS_SIZE             0x50
#define LOGIN_RESPONSE_SIZE     0x60
#define LOGIN_SIZE              0x80
#define CONNINFO_SIZE           0x90
#define CAPABILITIES_SIZE       0x42
#define RADIO_CAP_SIZE          0x66

// Variable size packets + payload
#define CIV_SIZE                0x15
#define AUDIO_SIZE            0x18
#define DATA_SIZE               0x15
```

### 2.2 Packing

```cpp
#pragma pack(push)
#pragma pack(1)
```

### 2.3 `control_packet` / `control_packet_t`

```cpp
typedef union control_packet {
    struct {
        quint32 len;
        quint16 type;
        quint16 seq;
        quint32 sentid;
        quint32 rcvdid;
    };
    char packet[CONTROL_SIZE];
} *control_packet_t;
```

### 2.4 `ping_packet` / `data_packet` (header 0x15)

```cpp
typedef union ping_packet {
    struct
    {
        quint32 len;        // 0x00
        quint16 type;       // 0x04
        quint16 seq;        // 0x06
        quint32 sentid;     // 0x08
        quint32 rcvdid;     // 0x0c
        quint8  reply;        // 0x10
        union { // This contains differences between the send/receive packet
            struct { // Ping packet
                quint32 time;      // 0x11 (uptime of device)
            };
            struct { // CIV header packet
                quint16 datalen;    // 0x11
                quint16 sendseq;    //0x13
            };
        };

    };
    char packet[PING_SIZE];
} *ping_packet_t, * data_packet_t, data_packet;
```

### 2.5 `openclose_packet`

```cpp
typedef union openclose_packet {
    struct
    {
        quint32 len;        // 0x00
        quint16 type;       // 0x04
        quint16 seq;        // 0x06
        quint32 sentid;     // 0x08
        quint32 rcvdid;     // 0x0c
        quint16 data;       // 0x10
        char unused;        // 0x11
        quint16 sendseq;    //0x13
        char magic;         // 0x15

    };
    char packet[OPENCLOSE_SIZE];
} *startstop_packet_t;
```

### 2.6 `token_packet`

```cpp
typedef union token_packet {
    struct
    {
        quint32 len;                // 0x00
        quint16 type;               // 0x04
        quint16 seq;                // 0x06
        quint32 sentid;             // 0x08 
        quint32 rcvdid;             // 0x0c
        quint32 payloadsize;      // 0x10
        quint8 requestreply;      // 0x14
        quint8 requesttype;       // 0x15
        quint16 innerseq;         // 0x16
        char unusedb[2];          // 0x18
        quint16 tokrequest;         // 0x1a
        quint32 token;              // 0x1c
        union {
            struct {
                quint16 authstartid;    // 0x20
                char unusedg2[2];       // 0x22
                quint16 resetcap;       // 0x24
                char unusedg1;          // 0x26
                quint16 commoncap;      // 0x27
                char unusedh;           // 0x29
                quint8 macaddress[6];   // 0x2a
            };
            quint8 guid[GUIDLEN];                  // 0x20
        };
        quint32 response;           // 0x30
        char unusede[12];           // 0x34
    };
    char packet[TOKEN_SIZE];
} *token_packet_t;
```

### 2.7 `status_packet`

```cpp
typedef union status_packet {
    struct
    {
        quint32 len;                // 0x00         0
        quint16 type;               // 0x04         4
        quint16 seq;                // 0x06         6
        quint32 sentid;             // 0x08         8
        quint32 rcvdid;             // 0x0c         12
        quint32 payloadsize;      // 0x10           18
        quint8 requestreply;      // 0x14           19
        quint8 requesttype;       // 0x15           20
        quint16 innerseq;         // 0x16           22
        char unusedb[2];          // 0x18
        quint16 tokrequest;         // 0x1a
        quint32 token;              // 0x1c 
        union {
            struct {
                quint16 authstartid;    // 0x20
                char unusedd[5];        // 0x22
                quint16 commoncap;      // 0x27
                char unusede;           // 0x29
                quint8 macaddress[6];     // 0x2a
            };
            quint8 guid[GUIDLEN];                  // 0x20
        };
        quint32 error;             // 0x30
        char unusedg[12];         // 0x34
        char disc;                // 0x40
        char unusedh;             // 0x41
        quint16 civport;          // 0x42 // Sent bigendian
        quint16 unusedi;          // 0x44 // Sent bigendian
        quint16 audioport;        // 0x46 // Sent bigendian
        char unusedj[7];          // 0x49
    };
    char packet[STATUS_SIZE];
} *status_packet_t;
```

### 2.8 `login_response_packet` (`login_response`)

```cpp
typedef union login_response_packet {
    struct
    {
        quint32 len;                // 0x00
        quint16 type;               // 0x04
        quint16 seq;                // 0x06
        quint32 sentid;             // 0x08 
        quint32 rcvdid;             // 0x0c
        quint32 payloadsize;      // 0x10
        quint8 requestreply;      // 0x14
        quint8 requesttype;       // 0x15
        quint16 innerseq;         // 0x16
        char unusedb[2];          // 0x18
        quint16 tokrequest;         // 0x1a
        quint32 token;              // 0x1c 
        quint16 authstartid;        // 0x20
        char unusedd[14];           // 0x22
        quint32 error;              // 0x30
        char unusede[12];           // 0x34
        char connection[16];        // 0x40
        char unusedf[16];           // 0x50
    };
    char packet[LOGIN_RESPONSE_SIZE];
} *login_response_packet_t;
```

### 2.9 `login_packet`

```cpp
typedef union login_packet {
    struct
    {
        quint32 len;                // 0x00
        quint16 type;               // 0x04
        quint16 seq;                // 0x06
        quint32 sentid;             // 0x08 
        quint32 rcvdid;             // 0x0c
        quint32 payloadsize;        // 0x10
        quint8 requestreply;        // 0x14
        quint8 requesttype;         // 0x15
        quint16 innerseq;           // 0x16
        char unusedb[2];            // 0x18
        quint16 tokrequest;         // 0x1a
        quint32 token;              // 0x1c 
        char unusedc[32];           // 0x20
        char username[16];          // 0x40
        char password[16];          // 0x50
        char name[16];              // 0x60
        char unusedf[16];           // 0x70
    };
    char packet[LOGIN_SIZE];
} *login_packet_t;
```

### 2.10 `conninfo_packet`

```cpp
typedef union conninfo_packet {
    struct
    {
        quint32 len;              // 0x00
        quint16 type;             // 0x04
        quint16 seq;              // 0x06
        quint32 sentid;           // 0x08 
        quint32 rcvdid;           // 0x0c
        quint32 payloadsize;      // 0x10
        quint8 requestreply;      // 0x14
        quint8 requesttype;       // 0x15
        quint16 innerseq;         // 0x16
        char unusedb[2];          // 0x18
        quint16 tokrequest;       // 0x1a
        quint32 token;            // 0x1c 
        union {
            struct {
                quint16 authstartid;    // 0x20
                char unusedg[5];        // 0x22
                quint16 commoncap;      // 0x27
                char unusedh;           // 0x29
                quint8 macaddress[6];     // 0x2a
            };
            quint8 guid[GUIDLEN];                  // 0x20
        };
        char unusedab[16];        // 0x30
        char name[32];                  // 0x40
        union { // This contains differences between the send/receive packet
            struct { // Receive
                quint32 busy;            // 0x60
                char computer[16];        // 0x64
                char unusedi[16];         // 0x74
                quint32 ipaddress;        // 0x84
                char unusedj[8];          // 0x78
            };
            struct { // Send
                char username[16];    // 0x60 
                char rxenable;        // 0x70
                char txenable;        // 0x71
                char rxcodec;         // 0x72
                char txcodec;         // 0x73
                quint32 rxsample;     // 0x74
                quint32 txsample;     // 0x78
                quint32 civport;      // 0x7c
                quint32 audioport;    // 0x80
                quint32 txbuffer;     // 0x84
                quint8 convert;      // 0x88
                char unusedl[7];      // 0x89
            };
        };
    };
    char packet[CONNINFO_SIZE];
} *conninfo_packet_t;
```

### 2.11 Packing (fin)

```cpp
#pragma pack(pop)
```

## 3) Code exact qui construit / parse les paquets (très important)

### 3.1 Handshake / contrôle

Source: `src/radio/icomudpbase.cpp` — `sendControl(...)`

```cpp
// Used to send idle and other "control" style messages
void icomUdpBase::sendControl(bool tracked = true, quint8 type = 0, quint16 seq = 0)
{
    control_packet p;
    memset(p.packet, 0x0, sizeof(p)); // We can't be sure it is initialized with 0x00!
    p.len = sizeof(p);
    p.type = type;
    p.sentid = myId;
    p.rcvdid = remoteId;

    if (!tracked) {
        p.seq = seq;
        udpMutex.lock();
        udp->writeDatagram(QByteArray::fromRawData((const char*)p.packet, sizeof(p)), radioIP, port);
        udpMutex.unlock();
    }
    else {
        sendTrackedPacket(QByteArray::fromRawData((const char*)p.packet, sizeof(p)));
    }
    return;
}
```

Source: `src/radio/icomudpbase.cpp` — `sendTrackedPacket(...)`

```cpp
void icomUdpBase::sendTrackedPacket(QByteArray d)
{
    // As the radio can request retransmission of these packets, store them in a buffer
    d[6] = sendSeq & 0xff;
    d[7] = (sendSeq >> 8) & 0xff;
    SEQBUFENTRY s;
    s.seqNum = sendSeq;
    s.timeSent = QTime::currentTime();
    s.retransmitCount = 0;
    s.data = d;
    if (txBufferMutex.tryLock(100))
    {

        if (sendSeq == 0) {
            // We are either the first ever sent packet or have rolled-over so clear the buffer.
            txSeqBuf.clear();
            congestion = 0;
        }
        if (txSeqBuf.size() > BUFSIZE)
        {
            txSeqBuf.erase(txSeqBuf.begin());
        }
        txSeqBuf.insert(sendSeq, s);

        txBufferMutex.unlock();
    }
    else {
        qInfo(logUdp()) << this->metaObject()->className() << ": txBuffer mutex is locked";
    }
    // Stop using purgeOldEntries() as it is likely slower than just removing the earliest packet.
    //qInfo(logUdp()) << this->metaObject()->className() << "RX:" << rxSeqBuf.size() << "TX:" <<txSeqBuf.size() << "MISS:" << rxMissing.size();
    //purgeOldEntries(); // Delete entries older than PURGE_SECONDS seconds (currently 5)
    sendSeq++;

    udpMutex.lock();
    udp->writeDatagram(d, radioIP, port);

    /*if (congestion > 10) { // Poor quality connection?
        udp->writeDatagram(d, radioIP, port);
        if (congestion > 20) // Even worse so send again.
            udp->writeDatagram(d, radioIP, port);
    } */
    if (idleTimer != Q_NULLPTR && idleTimer->isActive()) {
        idleTimer->start(IDLE_PERIOD); // Reset idle counter if it's running
    }
    udpMutex.unlock();
    packetsSent++;
    return;
}
```

Source: `src/radio/icomudpbase.cpp` — `dataReceived(QByteArray r)` (partie `CONTROL_SIZE` qui traite `0x04/0x06`)

```cpp
void icomUdpBase::dataReceived(QByteArray r)
{
    if (r.length() < 0x10)
    {
        return; // Packet too small do to anything with?
    }

    switch (r.length())
    {
    case (CONTROL_SIZE): // Empty response used for simple comms and retransmit requests.
    {
        control_packet_t in = (control_packet_t)r.constData();
        if (in->type == 0x01 && in->len == 0x10)
        {
            // Single packet request
            packetsLost++;
            congestion = static_cast<double>(packetsSent) / packetsLost * 100;
            txBufferMutex.lock();
            auto match = txSeqBuf.find(in->seq);
            if (match != txSeqBuf.end()) {
                // Found matching entry?
                // Send "untracked" as it has already been sent once.
                // Don't constantly retransmit the same packet, give-up eventually
                qDebug(logUdp()) << this->metaObject()->className() << ": Sending (single packet) retransmit of " << QString("0x%1").arg(match->seqNum, 0, 16);
                match->retransmitCount++;
                udpMutex.lock();
                udp->writeDatagram(match->data, radioIP, port);
                udpMutex.unlock();
            }
            else {
                qDebug(logUdp()) << this->metaObject()->className() << ": Remote requested packet"
                    << QString("0x%1").arg(in->seq, 0, 16) <<
                    "not found, have " << QString("0x%1").arg(txSeqBuf.firstKey(), 0, 16) <<
                    "to" << QString("0x%1").arg(txSeqBuf.lastKey(), 0, 16);
            }
            txBufferMutex.unlock();
        }
        if (in->type == 0x04) {
            qInfo(logUdp()) << this->metaObject()->className() << ": Received I am here ";
            areYouThereCounter = 0;
            // I don't think that we will ever receive an "I am here" other than in response to "Are you there?"
            remoteId = in->sentid;
            if (areYouThereTimer != Q_NULLPTR && areYouThereTimer->isActive()) {
                // send ping packets every second
                areYouThereTimer->stop();
            }
            sendControl(false, 0x06, 0x01); // Send Are you ready - untracked.
        }
        else if (in->type == 0x06)
        {
            // Just get the seqnum and ignore the rest.
        }
        break;
    }
```

Source: `src/radio/icomudphandler.cpp` — `dataReceived()` (partie `CONTROL_SIZE` qui traite `0x04/0x06`)

```cpp
            case (CONTROL_SIZE): // control packet
            {
                control_packet_t in = (control_packet_t)r.constData();
                if (in->type == 0x04) {
                    // If timer is active, stop it as they are obviously there!
                    qInfo(logUdp()) << this->metaObject()->className() << ": Received I am here from: " <<datagram.senderAddress().toString();

                    if (areYouThereTimer->isActive()) {
                        // send ping packets every second
                        areYouThereTimer->stop();
                        pingTimer->start(PING_PERIOD);
                        idleTimer->start(IDLE_PERIOD);
                    }
                }
                // This is "I am ready" in response to "Are you ready" so send login.
                else if (in->type == 0x06)
                {
                    qInfo(logUdp()) << this->metaObject()->className() << ": Received I am ready";
                    sendLogin(); // send login packet
                }
                break;
            }
```

Source: `src/radio/icomudphandler.cpp` — `sendAreYouThere()` (envoi du `0x03`)

```cpp
void icomUdpHandler::sendAreYouThere()
{
    if (areYouThereCounter == 20)
    {
        qInfo(logUdp()) << this->metaObject()->className() << ": Radio not responding.";
        status.message = "Radio not responding!";
    }
    qInfo(logUdp()) << this->metaObject()->className() << ": Sending Are You There...";

    areYouThereCounter++;
    icomUdpBase::sendControl(false,0x03,0x00);
}
```

### 3.2 Auth

Source: `src/radio/icomudphandler.cpp` — `sendLogin()`

```cpp
void icomUdpHandler::sendLogin() // Only used on control stream.
{

    qInfo(logUdp()) << this->metaObject()->className() << ": Sending login packet";

    tokRequest = static_cast<quint16>(rand() | rand() << 8); // Generate random token request.

    QByteArray usernameEncoded;
    QByteArray passwordEncoded;
    passcode(username, usernameEncoded);
    passcode(password, passwordEncoded);

    login_packet p;
    memset(p.packet, 0x0, sizeof(p)); // We can't be sure it is initialized with 0x00!
    p.len = sizeof(p);
    p.sentid = myId;
    p.rcvdid = remoteId;
    p.payloadsize = qToBigEndian((quint32)(sizeof(p) - 0x10));
    p.requesttype = 0x00;
    p.requestreply = 0x01;

    p.innerseq = qToBigEndian(authSeq++);
    p.tokrequest = tokRequest;
    memcpy(p.username, usernameEncoded.constData(), usernameEncoded.length());
    memcpy(p.password, passwordEncoded.constData(), passwordEncoded.length());
    memcpy(p.name, compName.toLocal8Bit().constData(), compName.length());

    sendTrackedPacket(QByteArray::fromRawData((const char*)p.packet, sizeof(p)));
    return;
}
```

Source: `src/radio/icomudphandler.cpp` — `sendToken(...)`

```cpp
void icomUdpHandler::sendToken(uint8_t magic)
{
    qDebug(logUdp()) << this->metaObject()->className() << "Sending Token request: " << magic;

    token_packet p;
    memset(p.packet, 0x0, sizeof(p)); // We can't be sure it is initialized with 0x00!
    p.len = sizeof(p);
    p.sentid = myId;
    p.rcvdid = remoteId;
    p.payloadsize = qToBigEndian((quint32)(sizeof(p) - 0x10));
    p.requesttype = magic;
    p.requestreply = 0x01;
    p.innerseq = qToBigEndian(authSeq++);
    p.tokrequest = tokRequest;
    p.resetcap = qToBigEndian((quint16)0x0798);
    p.token = token;

    sendTrackedPacket(QByteArray::fromRawData((const char *)p.packet, sizeof(p)));
    // The radio should request a repeat of the token renewal packet via retransmission!
    //tokenTimer->start(100); // Set 100ms timer for retry (this will be cancelled if a response is received)
    return;
}
```

Source: `src/radio/icomudphandler.cpp` — parsing `LOGIN_RESPONSE_SIZE`

```cpp
            case(LOGIN_RESPONSE_SIZE): // Response to Login packet.
            {
                login_response_packet_t in = (login_response_packet_t)r.constData();
                if (in->type != 0x01) {

                    connectionType = in->connection;
                    qInfo(logUdp()) << "Got connection type:" << connectionType;
                    if (connectionType == "FTTH")
                    {
                        highBandwidthConnection = true;
                    }

                    if (connectionType != "WFVIEW") // NOT WFVIEW
                    {
                        if (rxSetup.codec >= 0x40 || txSetup.codec >= 0x40)
                        {
                            emit haveNetworkError(errorType(QString("UDP"), QString("Opus codec not supported, forcing LPCM16")));
                            if (rxSetup.codec >= 0x40)
                                rxSetup.codec = 0x04;
                            if (txSetup.codec >= 0x40)
                                txSetup.codec = 0x04;
                        }
                    }


                    if (in->error == 0xfeffffff)
                    {
                        emit haveNetworkError(errorType(true, radioIP.toString(), "Invalid Username/Password"));
                        qInfo(logUdp()) << this->metaObject()->className() << ": Invalid Username/Password";
                    }
                    else if (!isAuthenticated)
                    {

                        if (in->tokrequest == tokRequest)
                        {
                            status.message="Radio Login OK!";
                            qInfo(logUdp()) << this->metaObject()->className() << ": Received matching token response to our request";
                            token = in->token;
                            sendToken(0x02);
                            tokenTimer->start(TOKEN_RENEWAL); // Start token request timer
                            isAuthenticated = true;
                        }
                        else
                        {
                            qInfo(logUdp()) << this->metaObject()->className() << ": Token response did not match, sent:" << tokRequest << " got " << in->tokrequest;
                        }
                    }

                    qInfo(logUdp()) << this->metaObject()->className() << ": Detected connection speed " << in->connection;
                }
                break;
            }
```

Source: `src/radio/icomudphandler.cpp` — parsing `TOKEN_SIZE`

```cpp
            case (TOKEN_SIZE): // Response to Token request
            {
                token_packet_t in = (token_packet_t)r.constData();
                if (in->requesttype == 0x05 && in->requestreply == 0x02 && in->type != 0x01)
                {
                    if (in->response == 0x0000)
                    {
                        qDebug(logUdp()) << this->metaObject()->className() << ": Token renewal successful";
                        tokenTimer->start(TOKEN_RENEWAL);
                        gotAuthOK = true;
                        if (!streamOpened)
                        {
                           sendRequestStream();
                        }

                    }
                    else if (in->response == 0xffffffff)
                    {
                        qWarning() << this->metaObject()->className() << ": Radio rejected token renewal, performing login";
                        remoteId = in->sentid;
                        tokRequest = in->tokrequest;
                        token = in->token;
                        streamOpened = false;
                        sendRequestStream();
                        // Got new token response
                        //sendToken(0x02); // Update it.
                    }
                    else
                    {
                        qWarning() << this->metaObject()->className() << ": Unknown response to token renewal? " << in->response;
                    }
                }
                break;
            }   
```

### 3.3 Streams

Source: `src/radio/icomudphandler.cpp` — `sendRequestStream()` (construction du `conninfo_packet`)

```cpp
void icomUdpHandler::sendRequestStream()
{

    QByteArray usernameEncoded;
    passcode(username, usernameEncoded);

    conninfo_packet p;
    memset(p.packet, 0x0, sizeof(p)); // We can't be sure it is initialized with 0x00!
    p.len = sizeof(p);
    p.sentid = myId;
    p.rcvdid = remoteId;
    p.payloadsize = qToBigEndian((quint32)(sizeof(p) - 0x10));
    p.requesttype = 0x03;
    p.requestreply = 0x01;

    if (!useGuid) {
        p.commoncap = 0x8010;
        memcpy(&p.macaddress, macaddress, 6);
    }
    else {
        memcpy(&p.guid, guid, GUIDLEN);
    }
    p.innerseq = qToBigEndian(authSeq++);
    p.tokrequest = tokRequest;
    p.token = token;
    memcpy(&p.name, devName.toLocal8Bit().constData(), devName.length());
    p.rxenable = 1;
    if (this->txSampleRates > 1) {
        p.txenable = 1;
        p.txcodec = txSetup.codec;
    }
    p.rxcodec = rxSetup.codec;
    memcpy(&p.username, usernameEncoded.constData(), usernameEncoded.length());
    p.rxsample = qToBigEndian((quint32)rxSetup.sampleRate);
    p.txsample = qToBigEndian((quint32)txSetup.sampleRate);
    p.civport = qToBigEndian((quint32)civLocalPort);
    p.audioport = qToBigEndian((quint32)audioLocalPort);
    p.txbuffer = qToBigEndian((quint32)txSetup.latency);
    p.convert = 1;
    sendTrackedPacket(QByteArray::fromRawData((const char*)p.packet, sizeof(p)));
    return;
}
```

Source: `src/radio/icomudphandler.cpp` — parsing `STATUS_SIZE` (extraction `civPort`/`audioPort`)

```cpp
            case (STATUS_SIZE):  // Status packet
            {
                status_packet_t in = (status_packet_t)r.constData();
                if (in->type != 0x01) {
                    if (in->error == 0xffffffff && !streamOpened)
                    {
                        emit haveNetworkError(errorType(true, radioIP.toString(), "Connection failed\ntry rebooting the radio."));
                        qInfo(logUdp()) << this->metaObject()->className() << ": Connection failed, wait a few minutes or reboot the radio.";
                    }
                    else if (in->error == 0x00000000 && in->disc == 0x01)
                    {
                        emit haveNetworkError(errorType(radioIP.toString(), "Got radio disconnected."));
                        qInfo(logUdp()) << this->metaObject()->className() << ": Got radio disconnected.";
                        if (streamOpened) {
                            // Close stream connections but keep connection open to the radio.
                            if (audio != Q_NULLPTR) {
                                delete audio;
                                audio = Q_NULLPTR;
                            }

                            if (civ != Q_NULLPTR) {
                                delete civ;
                                civ = Q_NULLPTR;
                            }

                            streamOpened = false;
                        }
                    }
                    else {
                        civPort = qFromBigEndian(in->civport);
                        audioPort = qFromBigEndian(in->audioport);
                        if (!streamOpened) {

                            civ = new icomUdpCivData(localIP, radioIP, civPort, splitWf, civLocalPort);
                            QObject::connect(civ, SIGNAL(receive(QByteArray)), this, SLOT(receiveFromCivStream(QByteArray)));

                            // TX is not supported
                            if (txSampleRates < 2) {
                                txSetup.sampleRate=0;
                                txSetup.codec = 0;
                            }
                            streamOpened = true;
                        }
                        if (audio == Q_NULLPTR) {
                            audio = new icomUdpAudio(localIP, radioIP, audioPort, audioLocalPort, rxSetup, txSetup);

                            QObject::connect(audio, SIGNAL(haveAudioData(audioPacket)), this, SLOT(receiveAudioData(audioPacket)));
                            QObject::connect(this, SIGNAL(haveChangeLatency(quint16)), audio, SLOT(changeLatency(quint16)));
                            QObject::connect(this, SIGNAL(haveSetVolume(quint8)), audio, SLOT(setVolume(quint8)));
                            QObject::connect(audio, SIGNAL(haveRxLevels(quint16, quint16, quint16, quint16, bool, bool)), this, SLOT(getRxLevels(quint16, quint16, quint16, quint16, bool, bool)));
                            QObject::connect(audio, SIGNAL(haveTxLevels(quint16, quint16, quint16, quint16, bool, bool)), this, SLOT(getTxLevels(quint16, quint16, quint16, quint16, bool, bool)));

                        }

                        qInfo(logUdp()) << this->metaObject()->className() << "Got serial and audio request success, device name: " << devName;


                    }
                }
                break;
            }
```

### 3.4 CI‑V encapsulé

Source: `src/radio/icomudpcivdata.cpp` — envoi CI‑V `send(QByteArray d)`

```cpp
void icomUdpCivData::send(QByteArray d)
{
    //qInfo(logUdp()) << "Sending: (" << d.length() << ") " << d;
    data_packet p;
    memset(p.packet, 0x0, sizeof(p)); // We can't be sure it is initialized with 0x00!
    p.len = (quint32)sizeof(p) + d.length();
    p.sentid = myId;
    p.rcvdid = remoteId;
    p.reply = (char)0xc1;
    p.datalen = d.length();
    p.sendseq = qToBigEndian(sendSeqB); // THIS IS BIG ENDIAN!

    QByteArray t = QByteArray::fromRawData((const char*)p.packet, sizeof(p));
    t.append(d);
    sendTrackedPacket(t);
    sendSeqB++;
    return;
}
```

Source: `src/radio/icomudpcivdata.cpp` — réception CI‑V `dataReceived()` (contrôle taille + extraction payload)

```cpp
void icomUdpCivData::dataReceived()
{
    while (udp->hasPendingDatagrams())
    {
        QNetworkDatagram datagram = udp->receiveDatagram();
        //qInfo(logUdp()) << "Received: " << datagram.data();
        QByteArray r = datagram.data();


        switch (r.length())
        {
        case (CONTROL_SIZE): // Control packet
        {
            control_packet_t in = (control_packet_t)r.constData();
            if (in->type == 0x04)
            {
                areYouThereTimer->stop();
            }
            else if (in->type == 0x06)
            {
                // Update remoteId
                remoteId = in->sentid;
                // Manually send a CIV start request and start the timer if it isn't received.
                // The timer will be stopped as soon as valid CIV data is received.
                sendOpenClose(false);
                if (startCivDataTimer != Q_NULLPTR) {
                    startCivDataTimer->start(100);
                }
            }
            break;
        }
        default:
        {
            if (r.length() > 21) {
                data_packet_t in = (data_packet_t)r.constData();
                if (in->type != 0x01) {
                    // Process this packet, any re-transmit requests will happen later.
                    //uint16_t gotSeq = qFromLittleEndian<quint16>(r.mid(6, 2));
                    // We have received some Civ data so stop sending Start packets!
                    if (startCivDataTimer != Q_NULLPTR) {
                        startCivDataTimer->stop();
                    }
                    lastReceived = QTime::currentTime();
                    if (quint16(in->datalen + 0x15) == (quint16)in->len)
                    {
                        //if (r.mid(0x15).length() != 157)
                        // Find data length
                        int pos = r.indexOf(QByteArrayLiteral("\x27\x00\x00")) + 2;
                        int len = r.mid(pos).indexOf(QByteArrayLiteral("\xfd"));
                        //splitWaterfall = false;
                        if (splitWaterfall && pos > 1 && len >= 490) {
                            // We need to split waterfall data into its component parts
                            // There are only 2 types that we are currently aware of
                            int numDivisions = 0;
                            int divSize = 50;
                            int splitPos = 12;
                            if (len == 490) // IC705, IC9700, IC7300(LAN), IC-905
                            {
                                numDivisions = 11;
                            }
                            else if (len == 492) // IC-905 in 10Ghz band
                            {
                                numDivisions = 11;
                                splitPos = 14;
                            }
                            else if (len == 704) // IC7610, IC7851, ICR8600
                            {
                                numDivisions = 15;
                            }
                            else {
                                qInfo(logUdp()) << "Unknown spectrum size" << len;
                                break;
                            }
                            // (sequence #1) includes center/fixed mode at [05]. No pixels.
                            // "INDEX: 00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 "
                            // "DATA:  27 00 00 01 11 01 00 00 00 14 00 00 00 35 14 00 00 fd "
                            // (sequences 2-10, 50 pixels)
                            // "INDEX: 00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49 50 51 52 53 54 55 "
                            // "DATA:  27 00 00 07 11 27 13 15 01 00 22 21 09 08 06 19 0e 20 23 25 2c 2d 17 27 29 16 14 1b 1b 21 27 1a 18 17 1e 21 1b 24 21 22 23 13 19 23 2f 2d 25 25 0a 0e 1e 20 1f 1a 0c fd "
                            //                  ^--^--(seq 7/11)
                            //                        ^-- start waveform data 0x00 to 0xA0, index 05 to 54
                            // (sequence #11)
                            // "INDEX: 00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 "
                            // "DATA:  27 00 00 11 11 0b 13 21 23 1a 1b 22 1e 1a 1d 13 21 1d 26 28 1f 19 1a 18 09 2c 2c 2c 1a 1b fd "

                            //int divSize = (len / numDivisions) + 6;
                            QByteArray wfPacket;
                            for (int i = 0; i < numDivisions; i++) {
                                wfPacket = r.mid(pos - 6, 9); // First part of packet 
                                char tens = ((i + 1) / 10);
                                char units = ((i + 1) - (10 * tens));
                                wfPacket[7] = units | (tens << 4);

                                tens = (numDivisions / 10);
                                units = (numDivisions - (10 * tens));
                                wfPacket[8] = units | (tens << 4);

                                if (i == 0) {
                                    //Just send initial data, first BCD encode the max number:
                                    wfPacket.append(r.mid(pos + 3, splitPos));
                                }
                                else
                                {
                                    wfPacket.append(r.mid((pos + splitPos+3) + ((i - 1) * divSize), divSize));
                                }
                                if (i < numDivisions - 1) {
                                    wfPacket.append('\xfd');
                                }
                                //qInfo(logUdp()) << "WF:" << wfPacket.toHex(' ');
                                emit receive(wfPacket);
                                wfPacket.clear();

                            }
                            //qInfo(logUdp()) << "IN:" << r.mid(0x15).toHex(' ');
                            //qInfo(logUdp()) << "Waterfall packet len" << len << "Num Divisions" << numDivisions << "Division Size" << divSize;
                        }
                        else {
                            // Not waterfall data or split not enabled.
                            emit receive(r.mid(0x15));
                        }
                        //qDebug(logUdp()) << "Got incoming CIV datagram" << r.mid(0x15).length();

                    }

                }
            }
            break;
        }
        }
        icomUdpBase::dataReceived(r); // Call parent function to process the rest.

        r.clear();
        datagram.clear();

    }
}
```

## 4) Détails de contexte (à compléter)

- OS (machine de dev ici): Windows (PowerShell).
- Connexion IC‑705: [à renseigner: mode AP du poste / via routeur ?]
- Valeurs utilisées: [à renseigner: IP du poste, username/password configurés “CI‑V Remote”]
