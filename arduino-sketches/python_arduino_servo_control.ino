// Last updated: 29 Dec 2024

#include <Servo.h>
#include <string.h>
#include <ArduinoJson.h>
// #include <LiquidCrystal_I2C.h>

// LiquidCrystal_I2C lcd(0x27,20,2);  // set the LCD address to 0x27 for a 16 chars and 2 line display

// Define servo objects for each axis
Servo servoX;  // Servo motor for X-axis
Servo servoY;  // Servo motor for Y-axis

// Define the pins to which the servos are connected
int servoXPin = 2;  // Connect servo for X-axis to pin 2
int servoYPin = 3;  // Connect servo for Y-axis to pin 3

int red = 9, green = 10, blue = 11, white = 12, orange = 13;

int lightPins[] = { red, green, blue, white, orange };

// Allocate the JSON document
JsonDocument doc;

const int numOfLeds = sizeof(lightPins)/sizeof(lightPins[0]);

byte lights[numOfLeds] = { 0 };
int x = 90, prevX = 90, y = 90, prevY = 90;
String toSend = "";
unsigned long ms;


void setup() {

  Serial.begin(57600);
  // lcd.init();
  // lcd.backlight();
  // lcd.clear();
  // lcd.write("Initializing...");

  for (int i = 0; i < numOfLeds; i++)
    pinMode(lightPins[i], OUTPUT);

  // Attach servos to their respective pins
  servoX.attach(servoXPin);
  servoY.attach(servoYPin);
  servoX.write(x);
  servoY.write(y);
  // delay(1000);
}

void loop() {

  if (Serial.available() > 0) {
    char data[100] = { 0 };
    // lcd.clear();

    // memset(data, 0, sizeof(data)); // Initialize the data buffer with null characters
    int dataLength = Serial.readBytesUntil('\n', data, sizeof(data) - 1);
    toSend = "Received: " + String(data);
    Serial.print(toSend);

    // Deserialize the JSON document
    DeserializationError error = deserializeJson(doc, data);

    // Test if parsing succeeds.
    if (error) {
      Serial.print(F("deserializeJson() failed: "));
      Serial.println(error.f_str());
      // return;
    } else {
      x = doc["x_axis"];
      y = doc["y_axis"];

      if (x == 0 && y == 0) {
        x = prevX;
        y = prevY;
      }


      int i = 0;

      Serial.print(" | Lights: ");
      // extract the values
      JsonArray array = doc["lights"].as<JsonArray>();
      for (JsonVariant v : array) {
        lights[i] = v.as<int>();
        Serial.print(lights[i]);
        Serial.print(", ");
        i++;
      }


      for (i = 0; i < numOfLeds; i++) {
        int pin = lightPins[i];

        if (pin == 3 || pin == 5 || pin == 6 || pin == 9 || pin == 10 || pin == 11)
          if (lights[i] == 255)
            digitalWrite(pin, 1);
          else
            analogWrite(pin, lights[i]);
        else if (lights[i] == 0)
          digitalWrite(pin, 0);
        else
          digitalWrite(pin, 1);
      }
      // String s = "x: " + String(x) + " y: " + String(y);

      toSend = " | Servo axis: {\"x\":" + String(x) + ", \"y\": " + String(y) + "}\n";

      Serial.println(toSend);
    }
  }

  if (x != prevX || y != prevY) {
    servoX.write(x);
    servoY.write(y);
    prevX = x;
    prevY = y;
  }

  // if (millis() - ms > 10) {
  //   ms = millis();
  //   toSend = " {\"x_axis\":" + String(x) + ", \"y_axis\": " + String(y) + "} \n";
  //   Serial.println(toSend);
  // }

  // servoTest2();
}



void servoTest() {
  servoX.write(0);
  delay(1000);
  servoX.write(90);
  delay(1000);
  servoX.write(180);
  delay(1000);
  servoX.write(90);
  delay(1000);
  servoY.write(0);
  delay(1000);
  servoY.write(90);
  delay(1000);
  servoY.write(180);
  delay(1000);
  servoY.write(90);
  delay(1000);
}

void servoTest2() {
  // Move servo on X-axis from 0 degrees to 180 degrees
  for (int angle = 0; angle <= 180; angle += 2) {
    servoX.write(angle);  // Move servo to specified angle
    delay(20);            // Delay for servo to reach position
  }

  // Move servo on X-axis from 180 degrees to 0 degrees
  for (int angle = 180; angle >= 0; angle -= 2) {
    servoX.write(angle);  // Move servo to specified angle
    delay(20);            // Delay for servo to reach position
  }

  // Move servo on Y-axis from 0 degrees to 90 degrees
  for (int angle = 0; angle <= 180; angle += 2) {
    servoY.write(angle);  // Move servo to specified angle
    delay(20);            // Delay for servo to reach position
  }

  // Move servo on Y-axis from 90 degrees to 0 degrees
  for (int angle = 180; angle >= 0; angle -= 2) {
    servoY.write(angle);  // Move servo to specified angle
    delay(20);            // Delay for servo to reach position
  }
}
