"""Read documentation contracts, calculate conditional corners, write JSON evidence.

Uses only the Python standard library. No CAD file is read or written.
Run with: python docs/a04/validate-electrical-contract.py
"""
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'docs' / 'a04'
contract_path = HERE / 'schematic-contract.json'
pin_path = HERE / 'pin-definitions.json'
contract = json.loads(contract_path.read_text(encoding='utf-8'))
definitions = json.loads(pin_path.read_text(encoding='utf-8'))
parts = {part['ref']: part for part in contract['components']}
assert len(parts) == len(contract['components']) == 72
assert sum(len(part['pins']) for part in parts.values()) == 239
for ref, mpn in [('U1', 'MDBT50Q-1MV2'), ('U2', 'BQ25186DLHR')]:
    definition = next(part for part in definitions['components'] if part['mpn'] == mpn)
    expected = {pin['number']: pin['recommendedNet'] for pin in definition['pins'] if pin['recommendedNet']}
    assert expected == parts[ref]['pins'], (ref, 'pin contract mismatch')
assert set(parts['U1']['pins']).isdisjoint(parts['U1']['noConnect'])
assert set(parts['U1']['pins']) | set(parts['U1']['noConnect']) == {str(n) for n in range(1, 62)}
assert parts['R22']['value'] == '3.3k'
assert parts['U6']['pins']['6'] == parts['U6']['pins']['10'] == '+3V0'
assert parts['U10']['pins']['7'] == 'NOR_RESET_N'

series = 3300.0
bias_min = 36.5e-6 - 25e-9
bias_max = 39.5e-6 + 25e-9
# These R/T bands are explicit assembly acceptance requirements, not a claim
# that independent R25/B25-85 tolerances guarantee the complete curve.
r0_min = 27280.0 * .97
r25_min = 10000.0 * .97
r40_max = 5827.0 * 1.03
v_cold_min = (r0_min + series * .99) * bias_min
v_room_min = (r25_min + series * .99) * bias_min
v_hot_max = (r40_max + series * 1.01) * bias_max
v_short_max = (series * 1.01) * bias_max
nominal_hot_r = .3945 / 38e-6 - series
nominal_cold_r = 1.0075 / 38e-6 - series
nominal_cold_exit_r = .820 / 38e-6 - series

def log_interpolate(r, t0, r0, t1, r1):
    return t0 + (t1 - t0) * math.log(r0 / r) / math.log(r0 / r1)

results = [
    dict(test='cold_stop_by_0_C', voltageV=v_cold_min, thresholdV=1.0575, marginV=v_cold_min-1.0575),
    dict(test='hot_stop_by_40_C', voltageV=v_hot_max, thresholdV=.387, marginV=.387-v_hot_max),
    dict(test='room_temperature_enable', voltageV=v_room_min, thresholdV=.404, marginV=v_room_min-.404),
    dict(test='shorted_sensor_denies_permission', voltageV=v_short_max, thresholdV=.387, marginV=.387-v_short_max),
]
assert all(result['marginV'] > 0 for result in results)
report = {
    'schemaVersion': 1,
    'scope': 'Documentation consistency and conditional arithmetic only; no CAD or physical qualification.',
    'inputSha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in [contract_path, pin_path]},
    'contractConsistency': {'status': 'PASS', 'pcbReferences': 72, 'connectedPinEndpoints': 239, 'moduleConnectedPins': 29, 'moduleNoConnectPins': 32, 'totalNoConnectPins': 35},
    'thermalStatus': 'CONDITIONAL ONLY: assembled sensor resistance, attachment, bias behavior and open fault require qualification.',
    'sources': {
        'charger': 'https://www.ti.com/lit/ds/symlink/bq25186.pdf',
        'comparator': 'https://www.ti.com/lit/ds/symlink/tlv6700.pdf',
        'sensor': 'https://www.semitec-global.com/uploads/2022/01/P12-13-AT-Thermistor.pdf',
    },
    'assumptions': {'seriesOhm': series, 'seriesTolerancePercent': 1, 'biasMinUa': 36.5, 'biasMaxUa': 39.5, 'comparatorLoadingWorstNa': 25, 'assemblyResistanceRequirementsOhm': {'at0CMin': r0_min, 'at25CMin': r25_min, 'at40CMax': r40_max}, 'attachmentLagIncluded': False},
    'conditionalCorners': results,
    'nominalEstimates': {
        'method': 'Log interpolation between manufacturer R/T table points; estimates only.',
        'hotEntryOhm': nominal_hot_r,
        'hotEntryC': log_interpolate(nominal_hot_r, 30, 8313, 40, 5827),
        'coldEntryOhm': nominal_cold_r,
        'coldEntryC': log_interpolate(nominal_cold_r, 0, 27280, 10, 17960),
        'coldRecoveryOhm': nominal_cold_exit_r,
        'coldRecoveryC': log_interpolate(nominal_cold_exit_r, 0, 27280, 10, 17960),
    },
    'dockLimiter': {'mpn': 'TPS2553DBVR', 'configuration': 'ILIM pin 5 tied directly to IN pin 1, not a resistor.', 'dcCurrentLimitMa': {'minimum': 50, 'typical': 75, 'maximum': 100}, 'limitDoesNotBoundTransientSurgeOrStoredCapacitorDischarge': True, 'source': 'https://www.ti.com/lit/ds/symlink/tps2553.pdf', 'sourcePages': [7, 15, 20]},
    'batteryApproval': False,
}
(HERE / 'electrical-validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2))
