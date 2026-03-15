# SubDivX Downloader

Buscador y descargador de subtítulos en español desde [subdivx.com](https://www.subdivx.com), operado desde la línea de comandos.

> El sitio usa protección Cloudflare, por lo que el script utiliza un navegador real (Brave o Chrome) via CDP (Chrome DevTools Protocol). Las cookies del navegador se copian automáticamente en cada ejecución para evitar bloqueos.

---

## Flujo de uso

1. Ejecutar el script pasando el nombre del archivo MKV
2. El script extrae el título, temporada y episodio automáticamente
3. Se muestra la lista de subtítulos disponibles en subdivx.com
4. Se selecciona el deseado con un número
5. El `.srt` se descarga, descomprime y renombra igual que el MKV

---

## Arquitectura: wrapper + script

El sistema tiene dos componentes:

- **`subdivx` (bash wrapper):** activa el entorno virtual, define el navegador y llama al script Python
- **`subdivx.py` (script Python):** contiene toda la lógica de búsqueda, login y descarga

El navegador se pasa como argumento al script, lo que permite cambiarlo editando solo el wrapper:

```bash
python3 /usr/local/bin/subdivx.py --brave "$@"          # usar Brave
python3 /usr/local/bin/subdivx.py --chrome "$@"         # usar Chrome
python3 /usr/local/bin/subdivx.py --browser-path "/ruta/exacta" "$@"  # ruta personalizada
```

---

## Navegadores compatibles

| Navegador     | Argumento        | Compatible | Notas |
|---------------|------------------|------------|-------|
| Brave         | `--brave`        | ✅         | Recomendado. Mejor compatibilidad con Cloudflare. |
| Google Chrome | `--chrome`       | ✅         | Compatible. Misma arquitectura que Brave. |
| Firefox       | —                | ❌         | No compatible. Usa un protocolo diferente a CDP. |

El script detecta el sistema operativo y usa la ruta de cookies correcta automáticamente:

| OS      | Navegador | Ruta de cookies |
|---------|-----------|-----------------|
| macOS   | Brave     | `~/Library/Application Support/BraveSoftware/Brave-Browser/Default` |
| macOS   | Chrome    | `~/Library/Application Support/Google/Chrome/Default` |
| Linux   | Brave     | `~/.config/BraveSoftware/Brave-Browser/Default` |
| Linux   | Chrome    | `~/.config/google-chrome/Default` |
| Windows | Brave     | `%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Default` |
| Windows | Chrome    | `%LOCALAPPDATA%\Google\Chrome\User Data\Default` |

---

## Instalación en macOS

### 1. Instalar Homebrew y Python

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python
python3 --version
```

### 2. Crear entorno virtual

```bash
python3 -m venv ~/.venv/subdivx
source ~/.venv/subdivx/bin/activate
```

### 3. Instalar dependencias

```bash
pip install playwright rich
playwright install chromium
```

### 4. Copiar el script

```bash
cp subdivx.py /usr/local/bin/subdivx.py
```

### 5. Crear el wrapper

```bash
cat > /usr/local/bin/subdivx << 'EOF'
#!/bin/bash
source ~/.venv/subdivx/bin/activate
python3 /usr/local/bin/subdivx.py --brave "$@"
EOF
chmod +x /usr/local/bin/subdivx
```

Para usar Chrome, reemplazar `--brave` por `--chrome`.

### 6. Primera ejecución

```bash
subdivx alguna.serie.S01E01.mkv
```

La primera vez el script solicita usuario y contraseña de subdivx.com (se guardan en `~/.config/subdivx.conf`) y pide hacer login manual en la ventana del navegador para guardar la sesión.

---

## Instalación en Windows

### 1. Instalar Python

Descargar desde [python.org/downloads](https://python.org/downloads). Durante la instalación marcar **Add Python to PATH**.

```
python --version
```

### 2. Crear entorno virtual

```powershell
python -m venv %USERPROFILE%\.venv\subdivx
%USERPROFILE%\.venv\subdivx\Scripts\activate
```

### 3. Instalar dependencias

```powershell
pip install playwright rich
playwright install chromium
```

### 4. Copiar el script

```powershell
mkdir C:\Scripts
copy subdivx.py C:\Scripts\subdivx.py
```

### 5. Crear el wrapper

Crear `C:\Windows\System32\subdivx.bat` con el siguiente contenido:

```bat
@echo off
call %USERPROFILE%\.venv\subdivx\Scripts\activate
python C:\Scripts\subdivx.py --brave %*
```

Para usar Chrome, reemplazar `--brave` por `--chrome`.

### 6. Primera ejecución

```powershell
subdivx alguna.serie.S01E01.mkv
```

---

## Instalación en Linux

### 1. Instalar Python

Debian/Ubuntu:
```bash
sudo apt update && sudo apt install python3 python3-venv python3-pip
```

Fedora/RHEL:
```bash
sudo dnf install python3 python3-venv
```

### 2. Crear entorno virtual

```bash
python3 -m venv ~/.venv/subdivx
source ~/.venv/subdivx/bin/activate
```

### 3. Instalar dependencias

```bash
pip install playwright rich
playwright install chromium
playwright install-deps chromium
```

### 4. Copiar el script

```bash
mkdir -p ~/.local/bin
cp subdivx.py ~/.local/bin/subdivx.py
```

### 5. Crear el wrapper

```bash
cat > ~/.local/bin/subdivx << 'EOF'
#!/bin/bash
source ~/.venv/subdivx/bin/activate
python3 ~/.local/bin/subdivx.py --brave "$@"
EOF
chmod +x ~/.local/bin/subdivx
```

Agregar `~/.local/bin` al PATH si es necesario (`~/.bashrc` o `~/.zshrc`):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### 6. Primera ejecución

```bash
subdivx alguna.serie.S01E01.mkv
```

---

## Uso diario

```bash
# Archivo con puntos en el nombre
subdivx Chicago.PD.S13E14.1080p.x265.mkv

# Archivo con espacios
subdivx "Breaking Bad S05E01 720p BluRay.mkv"

# Ruta completa
subdivx /ruta/completa/al/archivo.S02E03.mkv

# Carpeta completa (omite los MKV que ya tienen .srt)
subdivx /ruta/a/la/carpeta/

# Modo interactivo - navegador de carpetas
subdivx
```

### Comportamiento automático

- El nombre se procesa automáticamente: `Chicago.PD.S13E14.mkv` busca `Chicago PD S13E14`
- Si hay resultado exacto para el episodio se muestra solo ese; si no, muestra todos
- El `.srt` se renombra igual que el `.mkv` reemplazando la extensión
- Si el ZIP contiene múltiples `.srt`, el script pregunta cuál usar

---

## Solución de problemas

### Sin resultados para un archivo que existe en subdivx

- Verificar que el nombre sigue el patrón `TITULO.SXEXX.mkv` o `TITULO SxxExx.mkv`
- Cuando el script lo proponga, intentar con un término alternativo
- Si el subtítulo fue subido hace menos de una hora puede que no esté indexado todavía

### Error de Cloudflare o sesión expirada

Borrar el perfil separado del navegador y volver a ejecutar:

```bash
# macOS y Linux
rm -rf ~/.config/subdivx_brave_profile

# Windows
rmdir /s %USERPROFILE%\.config\subdivx_brave_profile
```

La primera vez volverá a pedir login manual en el navegador.

### El navegador no arranca o no se conecta

- Verificar que Brave o Chrome está instalado
- En Linux, asegurarse de haber ejecutado `playwright install-deps chromium`
- Para usar una ruta personalizada al ejecutable:

```bash
python3 subdivx.py --browser-path "/ruta/exacta/navegador" archivo.mkv
```

### El subtítulo no sincroniza con el video

Esto es un problema del subtítulo, no del script. Se recomienda elegir el que tenga más descargas y verificar en la descripción que mencione la versión del video que tenés.
