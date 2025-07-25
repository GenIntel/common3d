import numpy as np
import torch


def softmax(prob=None, T=0.07, C=1000):
    if prob is None:
        prob = 1.0 - torch.arange(101) / 100.0
    return torch.exp(prob / T) / (
        torch.exp(prob / T) + (C - 1) * torch.exp((1.0 - prob) / (T))
    )


def radians_per_feature_on_sphere(feats_count=1000, feats_dim=128):
    m = feats_dim / 2.0
    surface_sphere = (2.0 * (np.pi) ** m) / np.math.factorial(int(m - 1))
    alpha = ((surface_sphere) / feats_count) ** (1 / (2.0 * m - 1))
    return alpha


def degrees_per_feature_on_sphere(feats_count=1000, feats_dim=128):
    return (
        radians_per_feature_on_sphere(feats_count=feats_count, feats_dim=feats_dim)
        / (2 * np.pi)
        * 360
    )


def degree_to_cosine_similarity(deg):
    return np.cos(deg / 360.0 * 2.0 * np.pi)
