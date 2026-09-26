// Pro Micro NRF24 transmitter <-> Python RC controller bridge.
//
// Protocol (line oriented, '\n' terminated, ASCII):
//
//   Python -> Arduino (control frame, 11 fixed fields):
//     X1,Y1,X2,Y2,AUX1,AUX2,AUX3,AUX4,AUX5,AUX6,text\n
//     e.g. "127,220,127,127,0,0,1,0,0,1,ip\n"
//
//   Arduino -> Python (telemetry, rate-limited to 20 Hz or on message change):
//     T,<ping>,<pwm>,<message>\n
//     e.g. "T,12,80,192.168.1.42\n"
//
// Numeric values are decimal. `message` is the last field so embedded commas
// (unlikely) do not break parsing on the Python side.

#include <SPI.h>
#include "nRF24L01.h"
#include "RF24.h"

RF24 radio(9, 10);

const uint64_t addresses_w[2] = { 0xF0F0F0F0E1LL, 0xF0F0F0F0C1LL };
const uint64_t addresses_r[1] = { 0xF0F0F0F0D2LL };

struct __attribute__((packed)) SendData {
  byte X1;
  byte Y1;
  byte X2;
  byte Y2;
  byte AUX1;
  byte AUX2;
  byte AUX3;
  byte AUX4;
  byte AUX5;
  byte AUX6;
  int16_t TIME;
  char text[10];
};

struct __attribute__((packed)) ReceivedData {
  uint8_t PWM;
  int16_t TIME;
  char message[25];
};

SendData data;
ReceivedData recvData;

unsigned long lastRecvTime = 0;
unsigned long lastSerialTime = 0;
unsigned long lastRadioTxMs = 0;
unsigned long lastTelemMs = 0;

const unsigned long SERIAL_TIMEOUT_MS = 1000;
const unsigned long RADIO_TX_INTERVAL_MS = 10;   // 100 Hz to the car
const unsigned long TELEM_INTERVAL_MS = 50;      // 20 Hz back to Python

int pwm = 0;
int16_t ping = -1;
char lastMsgSent[25] = "";

#define jx1 A0
#define jy1 A1
#define jx2 A2
#define jy2 A3
#define jsw1 2
#define jsw2 4
#define sw1 5
#define sw2 6
#define sw3 7
#define sw4 8
#define LED 3

void useDefaultValues() {
  data.X1 = 127;
  data.Y1 = 127;
  data.X2 = 127;
  data.Y2 = 127;
  data.AUX1 = 0;
  data.AUX2 = 0;
  data.AUX3 = 0;
  data.AUX4 = 0;
  data.AUX5 = 0;
  data.AUX6 = 0;
  data.text[0] = '\0';
}

// strtok-based CSV field reader. Empty fields ("") yield 0 for numerics
// or "" for text. Returns false if the line is malformed (too few fields).
static bool parseControlCsv(char* line) {
  // Field order must match the protocol comment at the top of the file.
  char* fields[11];
  uint8_t idx = 0;

  // Manual split so trailing empty fields are preserved (strtok collapses them).
  char* p = line;
  fields[idx++] = p;
  while (*p && idx < 11) {
    if (*p == ',') {
      *p = '\0';
      fields[idx++] = p + 1;
    }
    p++;
  }
  if (idx < 11) {
    return false;
  }

  data.X1   = (byte)atoi(fields[0]);
  data.Y1   = (byte)atoi(fields[1]);
  data.X2   = (byte)atoi(fields[2]);
  data.Y2   = (byte)atoi(fields[3]);
  data.AUX1 = (byte)atoi(fields[4]);
  data.AUX2 = (byte)atoi(fields[5]);
  data.AUX3 = (byte)atoi(fields[6]);
  data.AUX4 = (byte)atoi(fields[7]);
  data.AUX5 = (byte)atoi(fields[8]);
  data.AUX6 = (byte)atoi(fields[9]);

  // Trim trailing CR from the text field (some hosts send \r\n).
  char* t = fields[10];
  size_t tlen = strlen(t);
  while (tlen > 0 && (t[tlen - 1] == '\r' || t[tlen - 1] == '\n')) {
    t[--tlen] = '\0';
  }
  strncpy(data.text, t, sizeof(data.text) - 1);
  data.text[sizeof(data.text) - 1] = '\0';
  return true;
}

static void sendTelemetry() {
  // Single-line CSV: "T,<ping>,<pwm>,<message>\n"
  Serial.print('T');
  Serial.print(',');
  Serial.print(ping);
  Serial.print(',');
  Serial.print(pwm);
  Serial.print(',');
  Serial.println(recvData.message);
  strncpy(lastMsgSent, recvData.message, sizeof(lastMsgSent) - 1);
  lastMsgSent[sizeof(lastMsgSent) - 1] = '\0';
  lastTelemMs = millis();
}

void setup() {
  Serial.begin(115200);

  pinMode(jsw1, INPUT_PULLUP);
  pinMode(jsw2, INPUT_PULLUP);
  pinMode(sw1, INPUT_PULLUP);
  pinMode(sw2, INPUT_PULLUP);
  pinMode(sw3, INPUT_PULLUP);
  pinMode(sw4, INPUT_PULLUP);
  pinMode(LED, OUTPUT);

  useDefaultValues();
  strcpy(recvData.message, "");
  recvData.PWM = 0;
  recvData.TIME = -1;

  radio.begin();
  radio.setAutoAck(false);
  radio.setDataRate(RF24_250KBPS);
  radio.setPALevel(RF24_PA_HIGH);
  radio.openWritingPipe(addresses_w[1]);
  radio.openReadingPipe(1, addresses_r[0]);
  radio.startListening();
}

void loop() {
  // ---- Serial in: CSV control frame ----
  if (Serial.available() > 0) {
    char serial_data[96] = { 0 };
    int n = Serial.readBytesUntil('\n', serial_data, sizeof(serial_data) - 1);
    if (n > 0) {
      serial_data[n] = '\0';
      if (parseControlCsv(serial_data)) {
        lastSerialTime = millis();
      }
      // Malformed frames are silently ignored to avoid polluting the line.
    }
  }

  // Fallback to neutral stick values if the host stops talking.
  if (millis() - lastSerialTime > SERIAL_TIMEOUT_MS) {
    useDefaultValues();
  }

  data.TIME = (int16_t)millis();

  // ---- Radio TX/RX at fixed cadence ----
  if (millis() - lastRadioTxMs >= RADIO_TX_INTERVAL_MS) {
    lastRadioTxMs = millis();

    radio.stopListening();
    radio.write(&data, sizeof(SendData));  // ignore return; autoAck is off
    radio.startListening();

    while (radio.available()) {
      radio.read(&recvData, sizeof(recvData));
      recvData.message[sizeof(recvData.message) - 1] = '\0';
      lastRecvTime = millis();
      ping = (int16_t)((int32_t)millis() - (int32_t)recvData.TIME);
    }
  }

  // Reset link state if the car has been silent for too long.
  if (millis() - lastRecvTime > 500) {
    recvData.PWM = 0;
    recvData.TIME = -1;
    recvData.message[0] = '\0';
    ping = -1;
  }

  // PWM-driven status LED tracks the receiver's reported PWM.
  pwm = map(recvData.PWM, 0, 255, 0, 80);
  analogWrite(LED, pwm);

  // ---- Telemetry out: rate-limited or on message change ----
  bool msgChanged = strcmp(lastMsgSent, recvData.message) != 0;
  if (msgChanged || (millis() - lastTelemMs) >= TELEM_INTERVAL_MS) {
    sendTelemetry();
  }
}
