# Syntetisk-kart

Prosjektet genererer syntetiske kartdata med GIS-klare lag.

## Kom i gang

Kjør første versjon av N50-kystkontur:

```bash
PYTHONPATH=src .venv/bin/python synthetic_map.py
```

For reproducerbar kjøring kan du også oppgi egen seed:

```bash
PYTHONPATH=src .venv/bin/python synthetic_map.py --seed 12345
```

## Testing

```bash
PYTHONPATH=src .venv/bin/python -m pytest
```
