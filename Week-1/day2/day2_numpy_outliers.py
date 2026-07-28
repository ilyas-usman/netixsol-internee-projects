import numpy as np

sensor = np.array([
    20, 21, 22, 23, 21,
    22, 20, 24, 23, 100
])

window = 3
rolling_mean = []
rolling_std = []

for i in range(len(sensor) - window + 1):
    current = sensor[i:i+window]

    rolling_mean.append(np.mean(current))
    rolling_std.append(np.std(current))

mean = np.mean(sensor)
std = np.std(sensor)
z_score = (sensor - mean) / std
outliers = sensor[np.abs(z_score) > 2]

print("Sensor Data:")
print(sensor)
print("\nRolling Mean:")
print(rolling_mean)
print("\nRolling Standard Deviation:")
print(rolling_std)
print("\nZ-Scores:")
print(z_score)
print("\nOutliers:")
print(outliers)