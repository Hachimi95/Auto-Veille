from auto_bulletin.utils import normalize_mitigations

sample = '''Mise à jour recommandée

"versions": [
"version 140.0.7339.80 ou ultérieure pour Linux",
"version 140.0.7339.80/81 ou ultérieure pour Windows",
"version 140.0.7339.80/81 ou ultérieure pour Mac"'''

print('INPUT:')
print(sample)
print('\nNORMALIZED OUTPUT:')
print(normalize_mitigations(sample))
