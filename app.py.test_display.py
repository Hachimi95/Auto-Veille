from auto_bulletin.utils import normalize_mitigations, clean_recommendation, clean_versions

sample = '''Mise à jour recommandée

"versions": [
"version 140.0.7339.80 ou ultérieure pour Linux",
"version 140.0.7339.80/81 ou ultérieure pour Windows",
"version 140.0.7339.80/81 ou ultérieure pour Mac"'''

print('RAW:')
print(sample)
print('\nNormalized:')
print(normalize_mitigations(sample))

from app import format_mitigation_for_display

normalized = normalize_mitigations(sample)
print('\nFormatted for display:')
print(format_mitigation_for_display(normalized))
