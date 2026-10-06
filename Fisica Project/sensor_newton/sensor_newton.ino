const int PIN_TRIG = 9;
const int PIN_ECHO = 10;

// Parámetros del experimento
const float DISTANCIA_OBJETIVO_CM = 70.0; // Distancia x según la guía (70 cm)
const float TOLERANCIA_INICIO_CM = 2.0;    // Detección de movimiento al soltar el carrito

enum EstadoExp { ESPERANDO_LANZAMIENTO, EN_CARRERA, FINALIZADO };
EstadoExp estado = ESPERANDO_LANZAMIENTO;

float distanciaInicial = 0;
unsigned long tiempoInicioMicros = 0;
unsigned long tiempoFinMicros = 0;

float medirDistanciaCM() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  long duracion = pulseIn(PIN_ECHO, HIGH, 30000); // Timeout de 30ms para evitar bloqueos
  if (duracion == 0) return -1.0;
  return (duracion * 0.0343) / 2.0;
}

void setup() {
  Serial.begin(9600);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);

  Serial.println("SISTEMA DE MEDICION DE MRUV - SEGUNDA LEY DE NEWTON");
  Serial.println("Coloque el carrito en el punto de partida (reposo)...");
  delay(2000);

  // Calibrar posición inicial
  float suma = 0;
  int lecturas = 0;
  for (int i = 0; i < 10; i++) {
    float d = medirDistanciaCM();
    if (d > 0) { suma += d; lecturas++; }
    delay(50);
  }
  distanciaInicial = suma / lecturas;

  Serial.print("Posicion inicial detectada: ");
  Serial.print(distanciaInicial);
  Serial.println(" cm.");
  Serial.println("Listo. Suelte el contrapeso para iniciar la toma...");
}

void loop() {
  float distanciaActual = medirDistanciaCM();
  if (distanciaActual <= 0) return; // Lectura descartada

  float recorrido = distanciaActual - distanciaInicial;

  switch (estado) {
    case ESPERANDO_LANZAMIENTO:
      // Si el carrito se desplaza más de 2 cm de su posición de reposo, inicia el cronómetro
      if (recorrido >= TOLERANCIA_INICIO_CM) {
        tiempoInicioMicros = micros();
        estado = EN_CARRERA;
        Serial.println(">> Movimiento detectado: Cronometro iniciado.");
      }
      break;

    case EN_CARRERA:
      // Cuando alcanza o supera los 70 cm del trayecto
      if (recorrido >= DISTANCIA_OBJETIVO_CM) {
        tiempoFinMicros = micros();
        estado = FINALIZADO;

        // Cálculo del tiempo transcurrido en segundos
        float tiempoSegundos = (tiempoFinMicros - tiempoInicioMicros) / 1000000.0;
        
        // Ecuación de cinemática con v0 = 0: a = (2 * x) / t^2
        float xMetros = DISTANCIA_OBJETIVO_CM / 100.0; // 0.70 m
        float aceleracion = (2.0 * xMetros) / (tiempoSegundos * tiempoSegundos);

        // Envío de resultados formateados
        Serial.println("----------------------------------------");
        Serial.println(">> RECORRIDO DE 70 CM COMPLETADO");
        Serial.print("Tiempo transcurrido (t): ");
        Serial.print(tiempoSegundos, 4);
        Serial.println(" s");
        Serial.print("Aceleracion calculada (a): ");
        Serial.print(aceleracion, 4);
        Serial.println(" m/s^2");
        
        // Formato CSV para volcado directo a base de datos / Excel:
        // TIEMPO,ACELERACION
        Serial.print("CSV_DATA:");
        Serial.print(tiempoSegundos, 4);
        Serial.print(",");
        Serial.println(aceleracion, 4);
        Serial.println("----------------------------------------");
        Serial.println("Para una nueva toma, presione el boton RESET del Arduino.");
      }
      break;

    case FINALIZADO:
      // Espera en reposo hasta que reinicien el circuito con el botón RESET
      break;
  }

  delay(15); // Muestreo rápido (~60 Hz) para no perder el instante de cruce
}