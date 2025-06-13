import logging

logger = logging.getLogger(__name__)
from torch import nn
from omegaconf import DictConfig
import torch
from od3d.cv.transforms.sequential import SequentialTransform
from od3d.cv.transforms.rgb_uint8_to_float import RGB_UInt8ToFloat
from od3d.cv.transforms.rgb_normalize import RGB_Normalize
from od3d.models.backbones.backbone import OD3D_Backbone
from od3d.data.batch_datatypes import OD3D_ModelData
from od3d.data.ext_enum import ExtEnum
from od3d.cv.visual.resize import resize
from typing import Tuple
import math
import types

from od3d.models.backbones.dino.dinov1 import (
    ViTExtractor,
)  # for selecting keys, querys, values


class DINOv2_WEIGHTS(str, ExtEnum):
    DEFAULT = "default"
    NONE = "none"


class DINOv2(OD3D_Backbone):
    def __init__(
        self,
        config: DictConfig,
    ):
        super().__init__(config=config)

        self.transform = SequentialTransform(
            [
                RGB_UInt8ToFloat(),
                RGB_Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ],
        )

        self.normalize = self.config.get("normalize", False)


        self.layers_returned = (
            config.layers_returned
        )  # choose from [0, 1] start with deepest (1)
        self.layers_count = len(self.layers_returned)

        # dino_vits8, dino_vitb8, dino_vits16, dino_vitb16, dinov2_vits14, dinov2_vitb14, dinov2_vitl14, dinov2_vitg14
        self.dinov2 = "dinov2" in self.config.hub_model
        import re

        self.patch_size = int(re.search(r"\d+$", self.config.hub_model).group())
        self.stride = self.config.get("stride", self.patch_size)
        if self.dinov2:
            self.extractor = torch.hub.load(
                self.config.hub_repo,
                self.config.hub_model,
                pretrained=self.config.weights == "default",
            )

            self.out_dims = [self.extractor.embed_dim]
            self.extractor = self.patch_vit_resolution(self.extractor, self.stride)

        else:  # using keys did not show any improvement
            self.extractor = ViTExtractor(model_type=self.config.hub_model)
            self.out_dims = [self.extractor.model.embed_dim]

        self.out_downsample_scales = []
        self.downsample_rate = self.config.downsample_rate
        import re

        match = re.match(r"dino[v2]*_vit[a-z]*([0-9]+)", self.config.hub_model, re.I)
        if match and len(match.groups()) == 1:
            self.dino_patch_size = int(match.groups()[0])
            self.downsample_rate_dino = int(match.groups()[0]) // (
                int(match.groups()[0]) // self.stride
            )
        else:
            msg = f"could not retrieve down sample rate dino from model name {self.config.hub_model}"
            raise Exception(msg)

        if self.freeze:
            for param in self.parameters():
                param.requires_grad = False

            # if not self.dinov2:
            #     for param in self.extractor.model.parameters():
            #         param.requires_grad = False

        if config.get("pca", None) is not None and config.pca.get("enable", False):
            self.pca_enabled = False
            pca_dim = config.pca.get("out_dim", 64)
            self.pca_layer = nn.Linear(self.out_dims[-1], pca_dim, bias=False)
            self.mean_features = nn.Parameter(torch.zeros(1, self.out_dims[-1]), requires_grad=False)
            for param in self.pca_layer.parameters():
                param.requires_grad = False
            nn.init.eye_(self.pca_layer.weight)
            self.out_dims[-1] = pca_dim
        else:
            self.pca_enabled = False

    def set_pca(self, dataset, transform, batch_size, num_workers, pin_memory, device):
        import copy
        from tqdm import tqdm
        from od3d.datasets.frame import OD3D_FRAME_MODALITIES
        from od3d.cv.geometry.objects3d.objects3d import PROJECT_MODALITIES
        self.pca_enabled = False
        self.eval()
        logger.info(f"Dataset contains {len(dataset)} frames.")


        if OD3D_FRAME_MODALITIES.PCL in dataset.modalities:
            dataset.modalities.remove(OD3D_FRAME_MODALITIES.PCL)
            add_pcl = True
        else:
            add_pcl = False

        dataset.transform = copy.deepcopy(transform)
        dataloader_train = torch.utils.data.DataLoader(
            dataset=dataset,
            batch_size=batch_size,
            shuffle=True,
            collate_fn=dataset.collate_fn,
            num_workers=num_workers,
            pin_memory=pin_memory,
        )

        if add_pcl:
            dataset.modalities.append(OD3D_FRAME_MODALITIES.PCL)

        net_feats_all = []
        net_feats_all_count = 0
        for i, batch in tqdm(enumerate(iter(dataloader_train))):
            batch.to(device=device)
            batch.cam_tform4x4_obj = batch.cam_tform4x4_obj.detach()
            logger.info(batch.category_id)
            with torch.no_grad():
                # B x F+N x C
                net_out = self(batch.rgb)

                feats2d_net = net_out.featmaps[-1]
                feats2d_net_mask = 1.0 * resize(
                    batch.mask,
                    H_out=feats2d_net.shape[2],
                    W_out=feats2d_net.shape[3],
                ) > 0.5
                net_feats_all.append(feats2d_net.permute(0, 2, 3, 1)[feats2d_net_mask[:, 0]])

                net_feats_all_count += net_feats_all[-1].shape[0]

                if net_feats_all_count > 500000:
                    break
        net_feats_all = torch.cat(net_feats_all, dim=0)

        #feature_vector_mean = net_feats_all.mean(dim=0)
        #logger.info(f"shape of mean feature vectors:{feature_vector_mean.shape}")
        #self.mean_features = feature_vector_mean

        #logger.info(
        #    f"shape of accumulated feature vectors:{net_feats_all.shape}",
        #)
        from od3d.cv.cluster.embed import pca
        pca_V = pca(net_feats_all, C=self.out_dims[-1], return_V=True)
        self.pca_layer.weight.copy_(pca_V.T)
        self.pca_enabled = True
        del net_feats_all

    def forward(self, x):
        if x.dim() == 3:
            C, H, W = x.shape
            B = 1
        elif x.dim() == 4:
            B, C, H, W = x.shape
        else:
            raise NotImplementedError

        H_out = H // self.downsample_rate
        W_out = W // self.downsample_rate
        H_out_expected = (
            ((H_out * self.downsample_rate_dino) - self.dino_patch_size) // self.stride
        ) + 1
        W_out_expected = (
            ((W_out * self.downsample_rate_dino) - self.dino_patch_size) // self.stride
        ) + 1
        offset_H = H_out - H_out_expected
        offset_H = self.round_up_to_even(offset_H)

        offset_W = W_out - W_out_expected
        offset_W = self.round_up_to_even(offset_W)
        H_in = H_out * self.downsample_rate_dino + offset_H * self.downsample_rate_dino
        W_in = W_out * self.downsample_rate_dino + offset_W * self.downsample_rate_dino

        x = resize(x, H_out=H_in, W_out=W_in)

        if self.dinov2:
            x_dict = self.extractor.forward_features(x)
            # # note: with layer normalization
            # x_feat_map = x_dict[
            #     "x_norm_patchtokens"
            # ] # 'x_norm_patchtokens', 'x_prenorm'[:, 1:]
            # x_feat_cls = x_dict["x_norm_clstoken"]

            # note: without layer normalization
            x_feat_map = x_dict[
                "x_prenorm"
            ][:, 1:] # 'x_norm_patchtokens', 'x_prenorm'[:, 1:]
            x_feat_cls = x_dict[
                "x_prenorm"
            ][:, 0]

        else:
            # x = self.extractor.get_intermediate_layers(x, n=12)[9]  # maximum 12 layers, zsp uses 9
            # x = x[:, 1:] # remove cls token

            x_feat_cat = self.extractor.extract_descriptors(
                batch=x,
                layer=9,
                facet="key",
                bin=False,
                include_cls=True,
            )
            x_feat_map = x_feat_cat[:, :, 1:]
            x_feat_cls = x_feat_cat[:, :, 0]
            # note: key layer 9 outperforms layer 9

        x_feat_map = x_feat_map.reshape(
            B,
            H_out_expected + offset_H,
            W_out_expected + offset_W,
            -1,
        ).permute(0, 3, 1, 2)

        x_feat_cls = x_feat_cls.reshape(
            B,
            1,
            1,
            -1,
        ).permute(0, 3, 1, 2)
        x_feat_map = x_feat_map[:, :, :H_out, :W_out]

        if self.normalize:
            x_feat_cls = x_feat_cls / (x_feat_cls.norm(dim=-3, keepdim=True) + 1e-10)
            x_feat_map = x_feat_map / (x_feat_map.norm(dim=-3, keepdim=True) + 1e-10)

        B, C, H, W = x_feat_map.shape
        if self.pca_enabled:
            x_feat_map = torch.flatten(x_feat_map, 2)
            x_feat_map = x_feat_map.permute(0, 2, 1)
            x_feat_map = x_feat_map - self.mean_features[(None,) * (x_feat_map.dim()-2)]
            x_feat_map = self.pca_layer(x_feat_map)
            x_feat_map = x_feat_map.permute(0, 2, 1)
            x_feat_map = x_feat_map.view(B, self.out_dims[-1], H, W)

            x_feat_cls = torch.flatten(x_feat_cls, 2)
            x_feat_cls = x_feat_cls.permute(0, 2, 1)
            x_feat_cls = x_feat_cls - self.mean_features[(None,) * (x_feat_cls.dim()-2)]
            x_feat_cls = self.pca_layer(x_feat_cls)
            x_feat_cls = x_feat_cls.permute(0, 2, 1)
            x_feat_cls = x_feat_cls.view(B, self.out_dims[-1], 1, 1)

            if self.normalize:
                x_feat_cls = x_feat_cls / (x_feat_cls.norm(dim=-3, keepdim=True) + 1e-10)
                x_feat_map = x_feat_map / (x_feat_map.norm(dim=-3, keepdim=True) + 1e-10)

        x_layers = []

        x_layers.append(x_feat_map)
        x_layers.append(x_feat_cls)

        x_layers = [x_layers[layer_id] for layer_id in self.layers_returned]

        if not self.config.get("head", True):
            x_layers = x_layers[0]

        x_out = OD3D_ModelData(featmaps=x_layers, feat=x_feat_cls[:, :, 0, 0])
        return x_out

    @staticmethod
    def round_up_to_even(num: int) -> int:
        return num if num % 2 == 0 else num + 1

    @staticmethod
    def _fix_pos_enc(patch_size: int, stride_hw: Tuple[int, int]):
        def interpolate_pos_encoding(self, x, w, h):
            previous_dtype = x.dtype
            npatch = x.shape[1] - 1
            N = self.pos_embed.shape[1] - 1
            if npatch == N and w == h:
                return self.pos_embed
            pos_embed = self.pos_embed.float()
            class_pos_embed = pos_embed[:, 0]
            patch_pos_embed = pos_embed[:, 1:]
            dim = x.shape[-1]
            # compute number of tokens taking stride into account
            w0 = 1 + (w - patch_size) // stride_hw[1]
            h0 = 1 + (h - patch_size) // stride_hw[0]
            assert (
                w0 * h0 == npatch
            ), f"""got wrong grid size for {h}x{w} with patch_size {patch_size} and
                                            stride {stride_hw} got {h0}x{w0}={h0 * w0} expecting {npatch}"""
            M = int(math.sqrt(N))  # Recover the number of patches in each dimension
            assert N == M * M
            kwargs = {}
            if self.interpolate_offset:
                # Historical kludge: add a small number to avoid floating point error in the interpolation, see https://github.com/facebookresearch/dino/issues/8
                # Note: still needed for backward-compatibility, the underlying operators are using both output size and scale factors
                sx = float(w0 + self.interpolate_offset) / M
                sy = float(h0 + self.interpolate_offset) / M
                kwargs["scale_factor"] = (sx, sy)
            else:
                # Simply specify an output size instead of a scale factor
                kwargs["size"] = (w0, h0)
            patch_pos_embed = nn.functional.interpolate(
                patch_pos_embed.reshape(1, M, M, dim).permute(0, 3, 1, 2),
                mode="bicubic",
                antialias=self.interpolate_antialias,
                **kwargs,
            )
            assert (w0, h0) == patch_pos_embed.shape[-2:]
            patch_pos_embed = patch_pos_embed.permute(0, 2, 3, 1).view(1, -1, dim)
            return torch.cat((class_pos_embed.unsqueeze(0), patch_pos_embed), dim=1).to(
                previous_dtype,
            )

        return interpolate_pos_encoding

    @staticmethod
    def patch_vit_resolution(model: nn.Module, stride: int) -> nn.Module:
        """
        change resolution of model output by changing the stride of the patch extraction.
        :param model: the model to change resolution for.
        :param stride: the new stride parameter.
        :return: the adjusted model
        """
        patch_size = model.patch_embed.patch_size[0]
        if stride == patch_size:  # nothing to do
            return model

        stride = nn.modules.utils._pair(stride)
        assert all(
            [(patch_size // s_) * s_ == patch_size for s_ in stride],
        ), f"stride {stride} should divide patch_size {patch_size}"

        # fix the stride

        model.patch_embed.proj.stride = stride
        # fix the positional encoding code
        model.interpolate_pos_encoding = types.MethodType(
            ViTExtractor._fix_pos_enc(patch_size, stride),
            model,
        )
        return model
