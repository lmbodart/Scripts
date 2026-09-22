#!/usr/bin/env python3
import argparse
import shutil
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Copia un directorio plantilla a un destino.")
    parser.add_argument("--origen", required=True, type=Path, help="Ruta de la carpeta origen a copiar")
    parser.add_argument("--destino", required=True, type=Path, help="Ruta del directorio de trabajo")
    
    args = parser.parse_args()

    if not args.origen.exists() or not args.origen.is_dir():
        print(f"La carpeta origen '{args.origen}' no existe.")
        exit(1)

    destino_final = args.destino / "foam"

    if destino_final.exists():
        print(f"La carpeta '{destino_final.name}' ya existe en este directorio. Omitiendo copia...")
        exit(0)

    try:
        # Copia la carpeta origen completa hacia el destino de trabajo
        shutil.copytree(args.origen, destino_final, dirs_exist_ok=True)

        # Si la carpeta '0' no existe, buscamos carpetas como '0.orig', '0.org', '0.config', etc.
        carpeta_0 = destino_final / "0"
        if not carpeta_0.exists():
            for item in destino_final.iterdir():
                if item.is_dir() and item.name.startswith("0."):
                    item.rename(carpeta_0)
                    break
        # Asegurar la presencia de polyMesh y triSurface en 'constant'
        constant_dir = destino_final / "constant"
        (constant_dir / "polyMesh").mkdir(parents=True, exist_ok=True)
        (constant_dir / "triSurface").mkdir(parents=True, exist_ok=True)

        print("Copia completada con éxito.\n")
    except Exception as e:
        print(f"Error al copiar: {e}")
        exit(1)

if __name__ == "__main__":
    main()