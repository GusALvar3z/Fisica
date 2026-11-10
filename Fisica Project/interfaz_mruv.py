import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial
import serial.tools.list_ports
import threading
import time
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class SistemaMRUVApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Sistema Automatizado de Medición y Almacenamiento en Tiempo Real - MRUV (UCV)")
        self.root.geometry("1280x800")
        self.root.configure(bg="#f4f6f9")

        # Variables de conexión y control
        self.puerto_serial = None
        self.conectado = False
        self.adquiriendo = False
        self.modo_simulacion = tk.BooleanVar(value=False)

        # Parámetros físicos y experimentales (Unidades SI)
        self.m1_var = tk.DoubleVar(value=0.045)   # Masa del carrito (kg)
        self.m2_var = tk.DoubleVar(value=0.010)   # Masa del contrapeso colgante (kg)
        self.g_var = tk.DoubleVar(value=9.81)     # Gravedad local (m/s^2)
        self.d0_var = tk.DoubleVar(value=0.750)   # Distancia inicial al sensor (m)
        self.ensayo_actual = tk.IntVar(value=1)   # Contador de ensayos (1 a 5)

        # Almacenamiento de datos
        self.datos_ensayo_actual = []  # Lista de tuplas (t, d, x)
        self.base_datos_total = []     # Filas completas de todos los ensayos guardados
        self.resumen_aceleraciones = {} # {ensayo: (a_exp, r2)}

        self._construir_interfaz()
        self.actualizar_puertos()
        self.calcular_aceleracion_teorica()

    def _construir_interfaz(self):
        # Marco superior: Título y Conexión Serial
        frame_top = tk.Frame(self.root, bg="#1e293b", pady=10, padx=15)
        frame_top.pack(fill=tk.X)

        lbl_titulo = tk.Label(
            frame_top,
            text="LABORATORIO DE FÍSICA: ADQUISICIÓN EN TIEMPO REAL PARA EL MRUV",
            fg="white", bg="#1e293b", font=("Segoe UI", 14, "bold")
        )
        lbl_titulo.pack(side=tk.LEFT)

        frame_conn = tk.Frame(frame_top, bg="#1e293b")
        frame_conn.pack(side=tk.RIGHT)

        tk.Checkbutton(
            frame_conn, text="Modo Simulación (Sin Arduino)", variable=self.modo_simulacion,
            bg="#1e293b", fg="#38bdf8", selectcolor="#0f172a", activebackground="#1e293b",
            font=("Segoe UI", 9, "bold")
        ).pack(side=tk.LEFT, padx=10)

        tk.Label(frame_conn, text="Puerto USB:", fg="white", bg="#1e293b", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=5)
        self.combo_puertos = ttk.Combobox(frame_conn, width=12, state="readonly")
        self.combo_puertos.pack(side=tk.LEFT, padx=5)

        btn_refrescar = tk.Button(frame_conn, text="↻", command=self.actualizar_puertos, bg="#334155", fg="white", relief=tk.FLAT, width=3)
        btn_refrescar.pack(side=tk.LEFT, padx=2)

        self.btn_conectar = tk.Button(
            frame_conn, text="Conectar Arduino", command=self.toggle_conexion,
            bg="#10b981", fg="white", font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=10
        )
        self.btn_conectar.pack(side=tk.LEFT, padx=8)

        # Contenedor principal dividido en Panel Izquierdo (Controles y Tabla) y Derecho (Gráficas)
        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg="#cbd5e1", sashwidth=5)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        panel_izq = tk.Frame(paned, bg="#f4f6f9", width=540)
        panel_der = tk.Frame(paned, bg="white", width=720)
        paned.add(panel_izq, stretch="never")
        paned.add(panel_der, stretch="always")

        # --- SUBPANEL IZQUIERDO 1: Parámetros Físicos y Control de Ensayos ---
        frame_params = tk.LabelFrame(panel_izq, text=" 1. Parámetros del Sistema (Máquina de Atwood Horizontal) ", bg="#f4f6f9", font=("Segoe UI", 10, "bold"), padx=10, pady=8)
        frame_params.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(frame_params, text="Masa carrito m₁ (kg):", bg="#f4f6f9").grid(row=0, column=0, sticky="w", pady=3)
        ent_m1 = ttk.Entry(frame_params, textvariable=self.m1_var, width=10)
        ent_m1.grid(row=0, column=1, padx=5, pady=3)
        ent_m1.bind("<KeyRelease>", lambda e: self.calcular_aceleracion_teorica())

        tk.Label(frame_params, text="Masa contrapeso m₂ (kg):", bg="#f4f6f9").grid(row=0, column=2, sticky="w", padx=5, pady=3)
        ent_m2 = ttk.Entry(frame_params, textvariable=self.m2_var, width=10)
        ent_m2.grid(row=0, column=3, padx=5, pady=3)
        ent_m2.bind("<KeyRelease>", lambda e: self.calcular_aceleracion_teorica())

        tk.Label(frame_params, text="Posición inicial d₀ (m):", bg="#f4f6f9").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(frame_params, textvariable=self.d0_var, width=10).grid(row=1, column=1, padx=5, pady=3)

        btn_calibrar = tk.Button(frame_params, text="Medir d₀ con Sensor", command=self.calibrar_d0, bg="#3b82f6", fg="white", relief=tk.FLAT, font=("Segoe UI", 8, "bold"))
        btn_calibrar.grid(row=1, column=2, columnspan=2, sticky="ew", padx=5, pady=3)

        # --- SUBPANEL IZQUIERDO 2: Botones de Operación ---
        frame_ctrl = tk.LabelFrame(panel_izq, text=" 2. Control de Adquisición (20 - 25 Hz) ", bg="#f4f6f9", font=("Segoe UI", 10, "bold"), padx=10, pady=8)
        frame_ctrl.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(frame_ctrl, text="N.º de Ensayo:", bg="#f4f6f9", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        spin_ensayo = ttk.Spinbox(frame_ctrl, from_=1, to=10, textvariable=self.ensayo_actual, width=6, font=("Segoe UI", 10, "bold"))
        spin_ensayo.grid(row=0, column=1, sticky="w", padx=5)

        self.btn_iniciar = tk.Button(
            frame_ctrl, text="▶ INICIAR ENSAYO", command=self.iniciar_ensayo,
            bg="#16a34a", fg="white", font=("Segoe UI", 10, "bold"), relief=tk.FLAT, padx=12, pady=4
        )
        self.btn_iniciar.grid(row=0, column=2, padx=5)

        self.btn_detener = tk.Button(
            frame_ctrl, text="■ DETENER Y PROCESAR", command=self.detener_ensayo,
            bg="#dc2626", fg="white", font=("Segoe UI", 10, "bold"), relief=tk.FLAT, padx=12, pady=4, state=tk.DISABLED
        )
        self.btn_detener.grid(row=0, column=3, padx=5)

        # --- SUBPANEL IZQUIERDO 3: Resultados Cinemáticos y Validación ---
        frame_res = tk.LabelFrame(panel_izq, text=" 3. Resultados del Ajuste Cuadrático y Validación ", bg="#f4f6f9", font=("Segoe UI", 10, "bold"), padx=10, pady=8)
        frame_res.pack(fill=tk.X, padx=5, pady=5)

        self.lbl_ateo = tk.Label(frame_res, text="Aceleración Teórica (a_teo): -- m/s²", bg="#f4f6f9", font=("Segoe UI", 9, "bold"), fg="#1e40af")
        self.lbl_ateo.grid(row=0, column=0, sticky="w", pady=2)

        self.lbl_aexp = tk.Label(frame_res, text="Aceleración Ensayo Actual (a_exp): -- m/s²", bg="#f4f6f9", font=("Segoe UI", 9, "bold"), fg="#047857")
        self.lbl_aexp.grid(row=0, column=1, sticky="w", padx=15, pady=2)

        self.lbl_ecuacion = tk.Label(frame_res, text="Polinomio x(t): --", bg="#f4f6f9", font=("Segoe UI", 9))
        self.lbl_ecuacion.grid(row=1, column=0, columnspan=2, sticky="w", pady=2)

        self.lbl_prom = tk.Label(frame_res, text="Promedio (ā_exp ± σ): -- m/s²  |  Error Relativo (%E): -- %", bg="#f4f6f9", font=("Segoe UI", 9, "bold"), fg="#b91c1c")
        self.lbl_prom.grid(row=2, column=0, columnspan=2, sticky="w", pady=4)

        # --- SUBPANEL IZQUIERDO 4: Tabla de Base de Datos Experimental ---
        frame_tabla = tk.LabelFrame(panel_izq, text=" 4. Base de Datos Experimental (Unidades SI) ", bg="#f4f6f9", font=("Segoe UI", 10, "bold"), padx=5, pady=5)
        frame_tabla.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        columnas = ("ensayo", "t", "d", "x", "vx", "a_exp", "obs")
        self.tabla = ttk.Treeview(frame_tabla, columns=columnas, show="headings", height=12)
        self.tabla.heading("ensayo", text="Ensayo")
        self.tabla.heading("t", text="t (s)")
        self.tabla.heading("d", text="d (m)")
        self.tabla.heading("x", text="x = d₀-d (m)")
        self.tabla.heading("vx", text="vₓ (m/s)")
        self.tabla.heading("a_exp", text="a_exp (m/s²)")
        self.tabla.heading("obs", text="Observación")

        anchos = [50, 60, 65, 80, 65, 75, 120]
        for col, ancho in zip(columnas, anchos):
            self.tabla.column(col, width=ancho, anchor="center")

        scroll_y = ttk.Scrollbar(frame_tabla, orient=tk.VERTICAL, command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll_y.set)
        self.tabla.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # Botones de exportación e higiene de datos
        frame_export = tk.Frame(panel_izq, bg="#f4f6f9", pady=5)
        frame_export.pack(fill=tk.X, padx=5)

        tk.Button(
            frame_export, text="📥 Exportar Base de Datos (.CSV / Excel)", command=self.exportar_datos,
            bg="#0284c7", fg="white", font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=10, pady=5
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            frame_export, text="🗑 Limpiar Todo", command=self.limpiar_base_datos,
            bg="#64748b", fg="white", font=("Segoe UI", 9), relief=tk.FLAT, padx=10, pady=5
        ).pack(side=tk.RIGHT, padx=5)

        # --- PANEL DERECHO: Gráficas Cinemáticas x(t) y vx(t) ---
        self.fig = Figure(figsize=(7, 6), dpi=100)
        self.fig.subplots_adjust(hspace=0.38, left=0.12, right=0.95, top=0.93, bottom=0.09)

        self.ax_pos = self.fig.add_subplot(211)
        self.ax_vel = self.fig.add_subplot(212)
        self._configurar_ejes_vacios()

        self.canvas = FigureCanvasTkAgg(self.fig, master=panel_der)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _configurar_ejes_vacios(self):
        self.ax_pos.clear()
        self.ax_pos.set_title("Posición vs. Tiempo: $x(t) = At^2 + Bt + C$", fontsize=11, fontweight="bold")
        self.ax_pos.set_xlabel("Tiempo $t$ (s)")
        self.ax_pos.set_ylabel("Desplazamiento $x$ (m)")
        self.ax_pos.grid(True, linestyle="--", alpha=0.6)

        self.ax_vel.clear()
        self.ax_vel.set_title("Velocidad Instantánea vs. Tiempo: $v_x(t) = v_{x0} + a_x t$", fontsize=11, fontweight="bold")
        self.ax_vel.set_xlabel("Tiempo $t$ (s)")
        self.ax_vel.set_ylabel("Velocidad $v_x$ (m/s)")
        self.ax_vel.grid(True, linestyle="--", alpha=0.6)

    def actualizar_puertos(self):
        puertos = [p.device for p in serial.tools.list_ports.comports()]
        self.combo_puertos["values"] = puertos
        if puertos:
            self.combo_puertos.current(0)

    def calcular_aceleracion_teorica(self):
        try:
            m1 = float(self.m1_var.get())
            m2 = float(self.m2_var.get())
            g = float(self.g_var.get())
            if (m1 + m2) > 0:
                a_teo = (m2 / (m1 + m2)) * g
                self.lbl_ateo.config(text=f"Aceleración Teórica (a_teo): {a_teo:.4f} m/s²")
                return a_teo
        except ValueError:
            pass
        return 0.0

    def toggle_conexion(self):
        if not self.conectado:
            puerto = self.combo_puertos.get()
            if not puerto:
                messagebox.showwarning("Puerto no seleccionado", "Selecciona un puerto COM o activa el 'Modo Simulación'.")
                return
            try:
                self.puerto_serial = serial.Serial(puerto, 9600, timeout=0.1)
                time.sleep(2)  # Esperar reinicio del Arduino Uno al abrir el puerto serial
                self.conectado = True
                self.btn_conectar.config(text="Desconectar", bg="#ef4444")
            except Exception as e:
                messagebox.showerror("Error de conexión", f"No se pudo abrir {puerto}:\n{e}")
        else:
            self.adquiriendo = False
            if self.puerto_serial and self.puerto_serial.is_open:
                self.puerto_serial.close()
            self.conectado = False
            self.btn_conectar.config(text="Conectar Arduino", bg="#10b981")

    def calibrar_d0(self):
        if self.modo_simulacion.get():
            self.d0_var.set(0.750)
            messagebox.showinfo("Calibración Simulada", "Posición inicial fijada en d₀ = 0.750 m")
            return

        if not self.conectado:
            messagebox.showwarning("Sin conexión", "Conecta el Arduino primero para medir d₀.")
            return

        try:
            self.puerto_serial.reset_input_buffer()
            self.puerto_serial.write(b'C')
            t0 = time.time()
            while time.time() - t0 < 2.0:
                linea = self.puerto_serial.readline().decode('utf-8', errors='ignore').strip()
                if linea.startswith("CAL:"):
                    valor_d0 = float(linea.split(":")[1])
                    self.d0_var.set(round(valor_d0, 4))
                    messagebox.showinfo("Calibración Exitosa", f"Distancia inicial medida: d₀ = {valor_d0:.4f} m")
                    return
        except Exception as e:
            messagebox.showerror("Error", f"Fallo al calibrar d₀: {e}")

    def iniciar_ensayo(self):
        if not self.modo_simulacion.get() and not self.conectado:
            messagebox.showwarning("Arduino no conectado", "Conecta tu placa Arduino Uno por USB o marca la casilla 'Modo Simulación'.")
            return

        self.datos_ensayo_actual.clear()
        self.adquiriendo = True
        self.btn_iniciar.config(state=tk.DISABLED)
        self.btn_detener.config(state=tk.NORMAL)

        if self.modo_simulacion.get():
            threading.Thread(target=self._hilo_simulacion, daemon=True).start()
        else:
            threading.Thread(target=self._hilo_lectura_serial, daemon=True).start()

    def _hilo_lectura_serial(self):
        try:
            self.puerto_serial.reset_input_buffer()
            self.puerto_serial.write(b'I')
            while self.adquiriendo:
                if self.puerto_serial.in_waiting > 0:
                    linea = self.puerto_serial.readline().decode('utf-8', errors='ignore').strip()
                    if linea == "FIN":
                        self.root.after(0, self.detener_ensayo)
                        break
                    partes = linea.split(",")
                    if len(partes) == 3:
                        try:
                            t_val = float(partes[0])
                            d_val = float(partes[1])
                            x_val = float(partes[2])
                            self.datos_ensayo_actual.append((t_val, d_val, x_val))
                        except ValueError:
                            continue
                time.sleep(0.005)
        except Exception as e:
            print(f"Error en lectura serial: {e}")
            self.root.after(0, self.detener_ensayo)

    def _hilo_simulacion(self):
        """Simula el recorrido del carrito (1.5 s, muestreo 45 ms) con una leve fricción realista."""
        a_teo = self.calcular_aceleracion_teorica()
        a_real_sim = a_teo * np.random.uniform(0.62, 0.68)  # Pérdida por roce con rieles de bajalenguas y polea
        d0 = float(self.d0_var.get())
        dt = 0.045  # 45 ms (~22.2 Hz)
        t = 0.0

        while self.adquiriendo:
            ruido_d = np.random.normal(0, 0.0012) if t > 0 else 0.0
            x_ideal = 0.5 * a_real_sim * (t ** 2)
            d_medido = max(0.050, d0 - x_ideal + ruido_d)
            x_medido = max(0.000, d0 - d_medido)

            self.datos_ensayo_actual.append((round(t, 3), round(d_medido, 4), round(x_medido, 4)))

            if d_medido <= 0.055:
                self.root.after(0, self.detener_ensayo)
                break

            time.sleep(dt)
            t += dt

    def detener_ensayo(self):
        if not self.adquiriendo:
            return
        self.adquiriendo = False

        if self.conectado and not self.modo_simulacion.get():
            try:
                self.puerto_serial.write(b'S')
            except Exception:
                pass

        self.btn_iniciar.config(state=tk.NORMAL)
        self.btn_detener.config(state=tk.DISABLED)

        if len(self.datos_ensayo_actual) >= 4:
            self.procesar_y_graficar_ensayo()
        else:
            messagebox.showwarning("Pocos datos", "No se capturaron suficientes lecturas válidas para el ajuste cuadrático.")

    def procesar_y_graficar_ensayo(self):
        ensayo_num = self.ensayo_actual.get()
        arr = np.array(self.datos_ensayo_actual)
        t_raw = arr[:, 0]
        d_raw = arr[:, 1]
        x_raw = arr[:, 2]

        # 1. Delimitación del intervalo de carrera (filtrado de puntos estáticos iniciales/finales)
        mask_mov = (x_raw >= 0.000) & (d_raw >= 0.045)
        t = t_raw[mask_mov]
        d = d_raw[mask_mov]
        x = x_raw[mask_mov]

        if len(t) < 4:
            t, d, x = t_raw, d_raw, x_raw

        # Reajustar origen temporal t0 = 0 s al primer dato válido de la carrera
        t = t - t[0]

        # 2. Ajuste de curvas por mínimos cuadrados: x(t) = A*t^2 + B*t + C
        coefs = np.polyfit(t, x, 2)
        A, B, C = coefs[0], coefs[1], coefs[2]
        a_exp = 2.0 * A  # Comparando con x(t) = (1/2)*a_x*t^2 + v_x0*t + x0

        # Coeficiente de determinación R^2
        x_pred = np.polyval(coefs, t)
        ss_res = np.sum((x - x_pred) ** 2)
        ss_tot = np.sum((x - np.mean(x)) ** 2)
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0

        # 3. Obtención de la velocidad instantánea por diferencias finitas: v_i = (x_{i+1} - x_i) / (t_{i+1} - t_i)
        vx = np.zeros_like(t)
        for i in range(1, len(t)):
            dt_paso = t[i] - t[i - 1]
            vx[i] = (x[i] - x[i - 1]) / dt_paso if dt_paso > 0 else 0.0

        # Guardar en base de datos y poblar tabla con el formato exacto del informe
        for i in range(len(t)):
            if i == 0:
                obs = "Inicio del movimiento"
                a_str = "—"
            elif i == len(t) - 1:
                obs = "Llegada al tope blanco"
                a_str = f"{a_exp:.3f}"
            else:
                obs = "Lectura válida"
                a_str = f"{a_exp:.3f}"

            fila_bd = {
                "Ensayo": ensayo_num,
                "Tiempo registrado t (s)": round(t[i], 3),
                "Distancia al sensor d (m)": round(d[i], 4),
                "Desplazamiento recorrido x=d0-d (m)": round(x[i], 4),
                "Velocidad instantánea vx (m/s)": round(vx[i], 3),
                "Aceleración experimental a_exp (m/s2)": a_str if a_str == "—" else round(a_exp, 3),
                "Observación": obs
            }
            self.base_datos_total.append(fila_bd)

            self.tabla.insert("", tk.END, values=(
                ensayo_num,
                f"{t[i]:.3f}",
                f"{d[i]:.3f}",
                f"{x[i]:.3f}",
                f"{vx[i]:.3f}",
                a_str,
                obs
            ))
        self.tabla.yview_moveto(1.0)

        # 4. Actualizar estadísticos y validación (%E)
        self.resumen_aceleraciones[ensayo_num] = (a_exp, r2)
        a_teo = self.calcular_aceleracion_teorica()

        self.lbl_aexp.config(text=f"Aceleración Ensayo {ensayo_num} (a_exp): {a_exp:.4f} m/s² (R² = {r2:.4f})")
        self.lbl_ecuacion.config(text=f"Polinomio Ensayo {ensayo_num}: x(t) = {A:.4f}t² + ({B:.4f})t + ({C:.4f})")

        lista_a = [val[0] for val in self.resumen_aceleraciones.values()]
        a_prom = np.mean(lista_a)
        a_std = np.std(lista_a, ddof=1) if len(lista_a) > 1 else 0.0
        err_porc = abs((a_teo - a_prom) / a_teo) * 100.0 if a_teo > 0 else 0.0

        self.lbl_prom.config(
            text=f"Promedio ({len(lista_a)} ensayos): ā_exp = {a_prom:.4f} ± {a_std:.4f} m/s²  |  Error Relativo (%E): {err_porc:.2f} %"
        )

        # 5. Actualizar gráficas cinemáticas x(t) y vx(t)
        self._configurar_ejes_vacios()
        t_suave = np.linspace(t[0], t[-1], 100)
        x_curva = np.polyval(coefs, t_suave)

        self.ax_pos.scatter(t, x, color="#2563eb", label=f"Datos experimentales (Ensayo {ensayo_num})", s=25, zorder=3)
        self.ax_pos.plot(t_suave, x_curva, color="#dc2626", linewidth=2,
                         label=f"Ajuste cuadrático: $x(t) = {A:.3f}t^2 + {B:.3f}t + {C:.3f}$ ($R^2={r2:.4f}$)")
        self.ax_pos.legend(loc="upper left", fontsize=9)

        # Ajuste lineal de velocidad vx(t)
        coefs_v = np.polyfit(t[1:], vx[1:], 1)
        v_recta = np.polyval(coefs_v, t_suave)
        self.ax_vel.scatter(t[1:], vx[1:], color="#059669", label="Velocidad por diferencias finitas", s=25, zorder=3)
        self.ax_vel.plot(t_suave, v_recta, color="#d97706", linestyle="--", linewidth=2,
                         label=f"Tendencia lineal: $v_x(t) = {coefs_v[0]:.3f}t + {coefs_v[1]:.3f}$")
        self.ax_vel.legend(loc="upper left", fontsize=9)

        self.canvas.draw()

        # Avanzar automáticamente el selector al siguiente ensayo (hasta 5)
        if ensayo_num < 5:
            self.ensayo_actual.set(ensayo_num + 1)

    def exportar_datos(self):
        if not self.base_datos_total:
            messagebox.showwarning("Base de datos vacía", "Realiza al menos un ensayo antes de exportar.")
            return

        ruta = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Archivo de Excel", "*.xlsx"), ("Archivo CSV", "*.csv")],
            initialfile="Base_Datos_MRUV_5_Ensayos.xlsx"
        )
        if not ruta:
            return

        df_datos = pd.DataFrame(self.base_datos_total)

        try:
            if ruta.endswith(".csv"):
                df_datos.to_csv(ruta, index=False, encoding="utf-8-sig")
            else:
                with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
                    df_datos.to_excel(writer, index=False, sheet_name="Datos_Cinemáticos_SI")

                    # Crear segunda hoja con el resumen de validación de los ensayos
                    a_teo = self.calcular_aceleracion_teorica()
                    filas_resumen = []
                    for ens, (a_val, r2_val) in sorted(self.resumen_aceleraciones.items()):
                        err_i = abs((a_teo - a_val) / a_teo) * 100.0 if a_teo > 0 else 0.0
                        filas_resumen.append({
                            "Ensayo": ens,
                            "Aceleración Teórica a_teo (m/s2)": round(a_teo, 4),
                            "Aceleración Experimental a_exp = 2A (m/s2)": round(a_val, 4),
                            "Coeficiente R^2": round(r2_val, 4),
                            "Error Relativo Porcentual (%E)": round(err_i, 2)
                        })
                    pd.DataFrame(filas_resumen).to_excel(writer, index=False, sheet_name="Resumen_Validación")

            messagebox.showinfo("Exportación Completada", f"Base de datos guardada correctamente en:\n{ruta}")
        except Exception as e:
            messagebox.showerror("Error al guardar", f"No se pudo exportar el archivo:\n{e}")

    def limpiar_base_datos(self):
        if messagebox.askyesno("Confirmar", "¿Deseas borrar todos los registros de la tabla y reiniciar al Ensayo 1?"):
            self.base_datos_total.clear()
            self.resumen_aceleraciones.clear()
            for item in self.tabla.get_children():
                self.tabla.delete(item)
            self.ensayo_actual.set(1)
            self._configurar_ejes_vacios()
            self.canvas.draw()
            self.lbl_aexp.config(text="Aceleración Ensayo Actual (a_exp): -- m/s²")
            self.lbl_ecuacion.config(text="Polinomio x(t): --")
            self.lbl_prom.config(text="Promedio (ā_exp ± σ): -- m/s²  |  Error Relativo (%E): -- %")


if __name__ == "__main__":
    root = tk.Tk()
    app = SistemaMRUVApp(root)
    root.mainloop()