import logging

logger = logging.getLogger(__name__)
from od3d.datasets.frame import OD3D_Frame
from od3d.cv.visual.crop import crop
from od3d.cv.transforms.transform import OD3D_Transform
from od3d.datasets.frame import OD3D_FRAME_MODALITIES
import torch


class Crop(OD3D_Transform):
    def __init__(self, H, W):
        super().__init__()
        self.H = H
        self.W = W

    def __call__(self, frame: OD3D_Frame):
        # logger.info(f"Frame name {self.name}")

        # _ = frame.size

        if OD3D_FRAME_MODALITIES.RGB in frame.modalities:
            scale = min(self.H / frame.H, self.W / frame.W)
            # scale = max(self.H / frame.H, self.W / frame.W)
            frame.size[0:1] = self.H
            frame.size[1:2] = self.W

            frame.rgb, cam_crop_tform_cam = crop(
                img=frame.get_rgb(),
                H_out=self.H,
                W_out=self.W,
                scale=scale,
            )

            frame.cam_intr4x4 = torch.bmm(
                cam_crop_tform_cam[None,],
                frame.get_cam_intr4x4()[None,],
            )[0]

            if OD3D_FRAME_MODALITIES.BBOX in frame.modalities:
                # x_min, y_min, x_max, y_max
                frame.bbox = (frame.get_bbox().reshape(2, 2) * scale[None,]).flatten()
                frame.bbox[[0, 2]] = frame.bbox[[0, 2]] + cam_crop_tform_cam[0, 2]
                frame.bbox[[1, 3]] = frame.bbox[[1, 3]] + cam_crop_tform_cam[1, 2]

            if OD3D_FRAME_MODALITIES.KPTS2D_ANNOT in frame.modalities:
                frame.kpts2d_annot = frame.get_kpts2d_annot() * scale[None,]
                frame.kpts2d_annot = frame.kpts2d_annot + cam_crop_tform_cam[:2, 2]

        if OD3D_FRAME_MODALITIES.RGBS in frame.modalities:
            for r in range(len(frame.get_rgbs())):
                scale = min(self.H / frame.sizes[r][0], self.W / frame.sizes[r][1])

                frame.sizes[r][0:1] = self.H
                frame.sizes[r][1:2] = self.W

                frame.rgbs[r], cam_crop_tform_cam = crop(
                    img=frame.get_rgbs()[r],
                    H_out=self.H,
                    W_out=self.W,
                    scale=scale,
                )

                frame.cam_intr4x4s[r] = torch.bmm(
                    cam_crop_tform_cam[None,],
                    frame.get_cam_intr4x4s()[r][None,],
                )[0]

                if OD3D_FRAME_MODALITIES.BBOXS in frame.modalities:
                    # x_min, y_min, x_max, y_max
                    frame.bboxs[r] = (
                        frame.get_bboxs()[r].reshape(2, 2) * scale[None,]
                    ).flatten()
                    frame.bboxs[r][[0, 2]] = (
                        frame.bboxs[r][[0, 2]] + cam_crop_tform_cam[0, 2]
                    )
                    frame.bboxs[r][[1, 3]] = (
                        frame.bboxs[r][[1, 3]] + cam_crop_tform_cam[1, 2]
                    )

                if OD3D_FRAME_MODALITIES.KPTS2D_ANNOTS in frame.modalities:
                    frame.kpts2d_annots[r] = frame.get_kpts2d_annots()[r] * scale[None,]
                    frame.kpts2d_annots[r] = (
                        frame.kpts2d_annots[r] + cam_crop_tform_cam[:2, 2]
                    )

        return frame
