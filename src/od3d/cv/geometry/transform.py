import logging

logger = logging.getLogger(__name__)

import torch
import math

# from kornia.geometry.liegroup import Se3, So3
# from kornia.geometry.quaternion import Quaternion
import od3d.cv.metric.pt3d_so3  # import so3_exp_map, so3_log_map
from od3d.cv.metric.pt3d_rotation_conversions import (
    rotation_6d_to_matrix,
    matrix_to_rotation_6d,
)


def transf4x4_to_rot4x4_without_scale(transf4x4):
    # note: note alignment of droid slam may include scale, therefore remove this scale.
    # note: projection does not change as we scale the depth z to the object as well
    rot4x4 = transf4x4.clone()
    scale = rot4x4[:3, :3].norm(dim=-1, keepdim=True).mean(dim=-2, keepdim=True)
    rot4x4[:3] = rot4x4[:3] / scale
    rot4x4[:3, 3] = 0.0
    return rot4x4


def so3_exp_map(so3_log: torch.Tensor):
    so3_log_shape = so3_log.shape
    so3_3x3 = od3d.cv.metric.pt3d_so3.so3_exp_map(so3_log.reshape(-1, 3))

    # so3_3x3 = Quaternion.from_axis_angle(axis_angle=so3_log.reshape(-1, 3)).matrix()

    # from kornia.geometry.conversions import axis_angle_to_rotation_matrix
    # so3_3x3 = axis_angle_to_rotation_matrix(axis_angle=so3_log.reshape(-1, 3))

    so3_3x3 = so3_3x3.reshape(so3_log_shape[:-1] + torch.Size([3, 3]))
    return so3_3x3


def so3_exp_map_tform4x4(so3_log: torch.Tensor):
    so3_3x3 = so3_exp_map(so3_log)
    return transf4x4_from_rot3x3(so3_3x3)


def rotation_6d_to_matrix(d6: torch.Tensor) -> torch.Tensor:
    """
    Converts 6D rotation representation by Zhou et al. [1] to rotation matrix
    using Gram--Schmidt orthogonalization per Section B of [1].
    Args:
        d6: 6D rotation representation, of size (*, 6)

    Returns:
        batch of rotation matrices of size (*, 3, 3)

    [1] Zhou, Y., Barnes, C., Lu, J., Yang, J., & Li, H.
    On the Continuity of Rotation Representations in Neural Networks.
    IEEE Conference on Computer Vision and Pattern Recognition, 2019.
    Retrieved from http://arxiv.org/abs/1812.07035
    """

    a1, a2 = d6[..., :3], d6[..., 3:]
    b1 = torch.nn.functional.normalize(a1, dim=-1)
    b2 = a2 - (b1 * a2).sum(-1, keepdim=True) * b1
    b2 = torch.nn.functional.normalize(b2, dim=-1)
    b3 = torch.cross(b1, b2, dim=-1)
    _rot3x3 = torch.stack((b1, b2, b3), dim=-2)

    # pytorch3d (rotation_6d_to_matrix) has different object axes
    _rot3x3 = _rot3x3[..., [0, 2, 1]]
    _rot3x3[..., 2] = -_rot3x3[..., 2]
    return _rot3x3


def matrix_to_rotation_6d(matrix: torch.Tensor) -> torch.Tensor:
    """
    Converts rotation matrices to 6D rotation representation by Zhou et al. [1]
    by dropping the last row. Note that 6D representation is not unique.
    Args:
        matrix: batch of rotation matrices of size (*, 3, 3)

    Returns:
        6D rotation representation, of size (*, 6)

    [1] Zhou, Y., Barnes, C., Lu, J., Yang, J., & Li, H.
    On the Continuity of Rotation Representations in Neural Networks.
    IEEE Conference on Computer Vision and Pattern Recognition, 2019.
    Retrieved from http://arxiv.org/abs/1812.07035
    """
    # pytorch3d (rotation_6d_to_matrix) has different object axes
    matrix[..., 2] = -matrix[..., 2]
    matrix = matrix[..., [0, 2, 1]]

    batch_dim = matrix.size()[:-2]
    return matrix[..., :2, :].clone().reshape(batch_dim + (6,))


def rot6d_to_rot3x3(rot6d: torch.Tensor):
    rot6d_shape = rot6d.shape
    _rot3x3 = rotation_6d_to_matrix(rot6d.reshape(-1, 6))
    return _rot3x3.reshape(rot6d_shape[:-1] + torch.Size([3, 3]))


def rot6d_to_tform4x4(rot6d: torch.Tensor):
    return transf4x4_from_rot3x3(rot6d_to_rot3x3(rot6d))


def so3_log_map(so3_3x3: torch.Tensor):
    so3_exp_shape = so3_3x3.shape

    so3_log = od3d.cv.metric.pt3d_so3.so3_log_map(so3_3x3.reshape(-1, 3, 3))

    so3_log = so3_log.reshape(so3_exp_shape[:-2] + torch.Size([3]))

    return so3_log


def rot3x3_to_rot6d(_rot3x3: torch.Tensor):
    rot3x3_shape = _rot3x3.shape
    _rot6d = matrix_to_rotation_6d(_rot3x3.reshape(-1, 3, 3))
    return _rot6d.reshape(rot3x3_shape[:-2] + torch.Size([6]))


def tform4x4_to_rot6d(_tform4x4: torch.Tensor):
    return rot3x3_to_rot6d(_tform4x4[..., :3, :3])


def se3_log_map(se3_exp: torch.Tensor):
    """
    Args:
        se3_exp (torch.Tensor): ...x4x4
    Returns:
        se3_log (torch.Tensor): ...x4x4
    """

    se3_exp_shape = se3_exp.shape

    # se3_log = pytorch3d.transforms.se3_log_map(
    #    se3_exp.reshape(-1, 4, 4).permute(0, 2, 1),
    # )

    # se3_log = Se3.from_matrix(se3_exp.reshape(-1, 4, 4)).log()
    # (transl :3, rot 3:6)
    so3_log = so3_log_map(se3_exp[..., :3, :3].reshape(-1, 3, 3))
    se3_log = torch.cat([se3_exp[..., :3, 3].reshape(-1, 3), so3_log], dim=-1)

    se3_log = se3_log.reshape(se3_exp_shape[:-2] + torch.Size([6]))

    return se3_log


def se3_exp_map(se3_log: torch.Tensor):
    """
    Args:
        se3_log (torch.Tensor): ...x6 (transl :3, rot 3:6)
    Returns:
        se3_4x4 (torch.Tensor): ...x4x4
    """
    se3_log_shape = se3_log.shape

    so3_3x3 = so3_exp_map(se3_log.reshape(-1, 6)[:, 3:6])
    se3_4x4 = transf4x4_from_rot3x3_and_transl3(
        rot3x3=so3_3x3,
        transl3=se3_log.reshape(-1, 6)[:, :3],
    )

    # se3_4x4 = Se3(rotation=Quaternion.from_axis_angle(axis_angle=se3_log.reshape(-1, 6)[:, 3:6]),
    #              translation=se3_log.reshape(-1, 6)[:, :3]).matrix()

    # se3_4x4 = pytorch3d.transforms.se3_exp_map(se3_log.reshape(-1, 6)).permute(0, 2, 1)

    se3_4x4 = se3_4x4.reshape(se3_log_shape[:-1] + torch.Size([4, 4]))

    return se3_4x4


def rot3x3_from_normal(normal: torch.Tensor):
    """Rotation matrix for rotating normal to vector [0.,-1.,0.]
    Args:
        normal (torch.Tensor): ...x3

    Returns:
        rot3x3 (torch.Tensor): ...x3x3
    """
    return rot3x3_from_two_vectors(
        a=normal,
        b=torch.Tensor([0.0, -1.0, 0.0])
        .to(device=normal.device, dtype=normal.dtype)
        .expand(normal.shape[:-1] + torch.Size([3])),
    )


def transf4x4_from_normal(normal: torch.Tensor):
    """Transformation matrix for rotating vector [0.,-1.,0.] onto normal
    Args:
        normal (torch.Tensor): ...x3

    Returns:
        transf4x4 (torch.Tensor): ...x4x4
    """

    return transf4x4_from_rot3x3(rot3x3_from_normal(normal))


def rot3x3_from_two_vectors(a: torch.Tensor, b: torch.Tensor):
    """Rotation matrix for rotating vector a onto vector b
    Args:
        a (torch.Tensor): ...x3
        b (torch.Tensor): ...x3

    Returns:
        rot3x3 (torch.Tensor): ...x3x3

    """

    v = torch.cross(
        a / a.norm(dim=-1, keepdim=True),
        b / b.norm(dim=-1, keepdim=True),
        dim=-1,
    )

    if a.dim() == 1:
        v = v[None,]
    rot3x3 = so3_exp_map(v)  # .transpose(-1, -2)

    if a.dim() == 1:
        rot3x3 = rot3x3[0]
    return rot3x3


def get_scale3d_tform4x4(a_tform4x4_b, keepdim=True):
    scale3d = torch.linalg.norm(a_tform4x4_b[..., :3, :3], dim=-1, keepdim=keepdim)
    return scale3d


def get_scale1d_tform4x4(a_tform4x4_b, keepdim=True):
    if keepdim:
        scale1d = get_scale3d_tform4x4(a_tform4x4_b, keepdim=keepdim).mean(
            dim=-2,
            keepdim=keepdim,
        )
    else:
        scale1d = get_scale3d_tform4x4(a_tform4x4_b, keepdim=keepdim).mean(
            dim=-1,
            keepdim=keepdim,
        )

    return scale1d


def scale3d_tform4x4(a_tform4x4_b, scale, clone=True):
    if clone:
        a_tform4x4_b = a_tform4x4_b.clone()
    a_tform4x4_b[..., :3, :3] = a_tform4x4_b[..., :3, :3] / (scale + 1e-7)
    return a_tform4x4_b


def scale1d_tform4x4_with_dist(a_tform4x4_b, clone=True):
    scale1d = get_scale1d_tform4x4(a_tform4x4_b=a_tform4x4_b, keepdim=True)
    if clone:
        a_tform4x4_b = a_tform4x4_b.clone()
    a_tform4x4_b[..., :3, :4] = a_tform4x4_b[..., :3, :4] / scale1d
    return a_tform4x4_b


def inv_tform4x4(a_tform4x4_b):
    scale = get_scale3d_tform4x4(a_tform4x4_b)
    # scale = torch.linalg.norm(a_tform4x4_b[..., :3, :3], dim=-1, keepdim=True)
    # scale_avg = scale.mean(dim=-2, keepdim=True)
    # if ((scale - scale_avg).abs() > 1e-3).any():
    #    scale_sel = scale[((scale - scale_avg).abs() > 1e-3)]
    #    logger.warning(f"Scale is not constant over all dimensions {scale_sel}")

    b_rot3x3_a = (a_tform4x4_b[..., :3, :3] / (scale**2 + 1e-7)).transpose(-1, -2)
    a_rot3x3_b_origin = a_tform4x4_b[..., :3, 3]
    b_transl3_0 = -rot3d(pts3d=a_rot3x3_b_origin, rot3x3=b_rot3x3_a)
    return transf4x4_from_rot3x3_and_transl3(transl3=b_transl3_0, rot3x3=b_rot3x3_a)


def rem_scale_tform4x4(a_tform4x4_b):
    scale = torch.linalg.norm(a_tform4x4_b[..., :3, :3], dim=-1, keepdim=True)
    a_tform4x4_b_wo_scale = a_tform4x4_b.clone()
    a_tform4x4_b_wo_scale[..., :3, :3] = a_tform4x4_b_wo_scale[..., :3, :3] / (
        scale + 1e-7
    )
    return a_tform4x4_b_wo_scale


# from od3d.cv.geometry.transform import inv_tform4x4
# import torch
# t = torch.Tensor([[0.0000, 2.1000, 0.0000, 1.0000],
#         [0.1000, 0.0000, 0.0000, 1.0000],
#         [0.0000, 0.0000, 3.1000, 0.0000],
#         [0.0000, 0.0000, 0.0000, 1.0000]])
# inv_tform4x4(t) - torch.linalg.pinv(t)


def tform4x4(tform1_4x4, tform2_4x4):
    return torch.bmm(
        tform1_4x4.reshape(-1, 4, 4),
        tform2_4x4.reshape(-1, 4, 4),
    ).reshape(tform1_4x4.shape)


def tform4x4_broadcast(a_tform4x4_b, b_tform4x4_c):
    shape_first_dims = torch.broadcast_shapes(
        a_tform4x4_b.shape[:-2],
        b_tform4x4_c.shape[:-2],
    )
    a_tform4x4_c = tform4x4(
        a_tform4x4_b.expand(*shape_first_dims, 4, 4),
        b_tform4x4_c.expand(*shape_first_dims, 4, 4),
    )
    return a_tform4x4_c


def rot3x3(rot1_3x3, rot2_3x3):
    return torch.bmm(rot1_3x3.reshape(-1, 3, 3), rot2_3x3.reshape(-1, 3, 3)).reshape(
        rot1_3x3.shape,
    )


def rot3x3_broadcast(a_rot3x3_b, b_rot3x3_c):
    shape_first_dims = torch.broadcast_shapes(
        a_rot3x3_b.shape[:-2],
        b_rot3x3_c.shape[:-2],
    )
    a_rot3x3_c = rot3x3(
        a_rot3x3_b.expand(*shape_first_dims, 3, 3),
        b_rot3x3_c.expand(*shape_first_dims, 3, 3),
    )
    return a_rot3x3_c


def make_device(device) -> torch.device:
    """
    Makes an actual torch.device object from the device specified as
    either a string or torch.device object. If the device is `cuda` without
    a specific index, the index of the current device is assigned.

    Args:
        device: Device (as str or torch.device)

    Returns:
        A matching torch.device object
    """
    device = torch.device(device) if isinstance(device, str) else device
    if device.type == "cuda" and device.index is None:
        # If cuda but with no index, then the current cuda device is indicated.
        # In that case, we fix to that device
        device = torch.device(f"cuda:{torch.cuda.current_device()}")
    return device


def format_tensor(
    input,
    dtype: torch.dtype = torch.float32,
    device="cpu",
) -> torch.Tensor:
    """
    Helper function for converting a scalar value to a tensor.

    Args:
        input: Python scalar, Python list/tuple, torch scalar, 1D torch tensor
        dtype: data type for the input
        device: Device (as str or torch.device) on which the tensor should be placed.

    Returns:
        input_vec: torch tensor with optional added batch dimension.
    """
    device_ = make_device(device)
    if not torch.is_tensor(input):
        input = torch.tensor(input, dtype=dtype, device=device_)

    if input.dim() == 0:
        input = input.view(1)

    if input.device == device_:
        return input

    input = input.to(device=device)
    return input


def convert_to_tensors_and_broadcast(
    *args,
    dtype: torch.dtype = torch.float32,
    device="cpu",
):
    """
    Helper function to handle parsing an arbitrary number of inputs (*args)
    which all need to have the same batch dimension.
    The output is a list of tensors.

    Args:
        *args: an arbitrary number of inputs
            Each of the values in `args` can be one of the following
                - Python scalar
                - Torch scalar
                - Torch tensor of shape (N, K_i) or (1, K_i) where K_i are
                  an arbitrary number of dimensions which can vary for each
                  value in args. In this case each input is broadcast to a
                  tensor of shape (N, K_i)
        dtype: data type to use when creating new tensors.
        device: torch device on which the tensors should be placed.

    Output:
        args: A list of tensors of shape (N, K_i)
    """
    # Convert all inputs to tensors with a batch dimension
    args_1d = [format_tensor(c, dtype, device) for c in args]

    # Find broadcast size
    sizes = [c.shape[0] for c in args_1d]
    N = max(sizes)

    args_Nd = []
    for c in args_1d:
        if c.shape[0] != 1 and c.shape[0] != N:
            msg = "Got non-broadcastable sizes %r" % sizes
            raise ValueError(msg)

        # Expand broadcast dim and keep non broadcast dims the same size
        expand_sizes = (N,) + (-1,) * len(c.shape[1:])
        args_Nd.append(c.expand(*expand_sizes))

    return args_Nd


def look_at_rotation(
    camera_position,
    at=((0, 0, 0),),
    up=((0, 1, 0),),
    device="cpu",
) -> torch.Tensor:
    """
    This function takes a vector 'camera_position' which specifies the location
    of the camera in world coordinates and two vectors `at` and `up` which
    indicate the position of the object and the up directions of the world
    coordinate system respectively. The object is assumed to be centered at
    the origin.

    The output is a rotation matrix representing the transformation
    from world coordinates -> view coordinates.

    Args:
        camera_position: position of the camera in world coordinates
        at: position of the object in world coordinates
        up: vector specifying the up direction in the world coordinate frame.

    The inputs camera_position, at and up can each be a
        - 3 element tuple/list
        - torch tensor of shape (1, 3)
        - torch tensor of shape (N, 3)

    The vectors are broadcast against each other so they all have shape (N, 3).

    Returns:
        R: (N, 3, 3) batched rotation matrices
    """
    # Format input and broadcast
    broadcasted_args = convert_to_tensors_and_broadcast(
        camera_position,
        at,
        up,
        device=device,
    )
    camera_position, at, up = broadcasted_args
    for t, n in zip([camera_position, at, up], ["camera_position", "at", "up"]):
        if t.shape[-1] != 3:
            msg = "Expected arg %s to have shape (N, 3); got %r"
            raise ValueError(msg % (n, t.shape))
    z_axis = torch.nn.functional.normalize(at - camera_position, eps=1e-5)
    x_axis = torch.nn.functional.normalize(torch.cross(up, z_axis, dim=1), eps=1e-5)
    y_axis = torch.nn.functional.normalize(torch.cross(z_axis, x_axis, dim=1), eps=1e-5)
    is_close = torch.isclose(x_axis, torch.tensor(0.0), atol=5e-3).all(
        dim=1,
        keepdim=True,
    )
    if is_close.any():
        replacement = torch.nn.functional.normalize(
            torch.cross(y_axis, z_axis, dim=1),
            eps=1e-5,
        )
        x_axis = torch.where(is_close, replacement, x_axis)
    R = torch.cat((x_axis[:, None, :], y_axis[:, None, :], z_axis[:, None, :]), dim=1)
    return R.transpose(1, 2)


def transf4x4_from_pos_and_theta(pos, theta):
    in_shape = theta.shape
    dtype = theta.dtype
    device = theta.device
    zeros = torch.zeros(size=in_shape, dtype=dtype, device=device).reshape(-1)
    ones = torch.ones(size=in_shape, dtype=dtype, device=device).reshape(-1)
    camrot_pos_rot3x3_obj = look_at_rotation(
        pos,
        up=((0, 0, 1),),
        device=pos.device,
    ).transpose(
        -1,
        -2,
    )  # pytorch3d convention to store rotation matrix transposed
    camrot_pos_rot3x3_obj[..., 0:2, :] = -camrot_pos_rot3x3_obj[
        ...,
        0:2,
        :,
    ]  # pytorch3d convention to have negative x,y axis

    camrot_theta_rot3x3_camrot_pos = (
        torch.stack(
            [
                torch.cos(theta),
                -torch.sin(theta),
                zeros,
                torch.sin(theta),
                torch.cos(theta),
                zeros,
                zeros,
                zeros,
                ones,
            ],
            dim=-1,
        )
        .reshape(-1, 3, 3)
        .transpose(-1, -2)
    )  # transpose is required because theta is usually given in -z axis instead of +z

    camrot_rot3x3_obj = torch.bmm(camrot_theta_rot3x3_camrot_pos, camrot_pos_rot3x3_obj)
    camrot_transl3_obj = rot3d(pts3d=-pos, rot3x3=camrot_rot3x3_obj)
    camrot_tform4x4_obj = transf4x4_from_rot3x3_and_transl3(
        camrot_rot3x3_obj,
        camrot_transl3_obj,
    )

    return camrot_tform4x4_obj

    # dist = pos.norm(dim=-1)
    # azim = torch.atan(pos[..., 0] / -pos[..., 1]) % math.pi + math.pi * (pos[..., 0] < 0) # torch.atan(pos[..., 0] / pos[..., 2])  % math.pi + math.pi * (pos[..., 0] < 0)
    # elev = torch.asin(pos[..., 2] / dist)
    # return transf4x4_from_spherical(azim=azim, elev=elev, theta=theta, dist=dist)


def get_spherical_uniform_tform4x4(
    azim_min=-math.pi,
    azim_max=math.pi,
    azim_steps=5,
    elev_min=-math.pi / 2,
    elev_max=math.pi / 2,
    elev_steps=5,
    theta_min=-math.pi / 2,
    theta_max=math.pi / 2,
    theta_steps=5,
    device="cpu",
):
    azim = torch.linspace(start=azim_min, end=azim_max, steps=azim_steps).to(
        device=device,
    )  # 12
    elev = torch.linspace(start=elev_min, end=elev_max, steps=elev_steps).to(
        device=device,
    )  # start=-torch.pi / 6, end=torch.pi / 3, steps=4
    theta = torch.linspace(start=theta_min, end=theta_max, steps=theta_steps).to(
        device=device,
    )  # -torch.pi / 6, end=torch.pi / 6, steps=3

    # dist = torch.linspace(start=eval(config_sample.uniform.dist.min), end=eval(config_sample.uniform.dist.max), steps=config_sample.uniform.dist.steps).to(
    #    device=self.device)
    dist = torch.linspace(start=1.0, end=1.0, steps=1).to(device=device)

    azim_shape = azim.shape
    elev_shape = elev.shape
    theta_shape = theta.shape
    dist_shape = dist.shape
    in_shape = azim_shape + elev_shape + theta_shape + dist_shape
    azim = azim[:, None, None, None].expand(in_shape).reshape(-1)
    elev = elev[None, :, None, None].expand(in_shape).reshape(-1)
    theta = theta[None, None, :, None].expand(in_shape).reshape(-1)
    dist = dist[None, None, None, :].expand(in_shape).reshape(-1)
    cams_multiview_tform4x4_cuboid = transf4x4_from_spherical(
        azim=azim,
        elev=elev,
        theta=theta,
        dist=dist,
    )

    return cams_multiview_tform4x4_cuboid


def get_cam_tform4x4_obj_for_viewpoints_count(
    viewpoints_count=1,
    dist: float = 1.0,
    device=None,
    dtype=None,
    spiral=False,
):
    if not spiral:
        if viewpoints_count == 1:
            # front:
            # azim = torch.Tensor([0.0])
            # elev = torch.Tensor([0.0])
            # theta = torch.Tensor([0.0])

            # front right
            azim = torch.Tensor([-math.pi / 3.5])
            elev = torch.Tensor([math.pi / 12])
            theta = torch.Tensor([0.0])

        elif viewpoints_count == 2:
            # front, top
            # azim = torch.Tensor([0.0, 0.0])
            # elev = torch.Tensor([0.0, math.pi / 2.0 - 0.01])
            # theta = torch.Tensor([0.0, 0.0])

            # front right, back left
            azim = torch.Tensor([-math.pi / 10, math.pi - math.pi / 10 - math.pi / 2])
            elev = torch.Tensor([math.pi / 12, math.pi / 12])
            theta = torch.Tensor([0.0, 0.0])

        elif viewpoints_count == 3:
            # front, top, right
            azim = torch.Tensor([0.0, 0.0, math.pi / 2.0])
            elev = torch.Tensor([0.0, math.pi / 2.0 - 0.01, 0.0])
            theta = torch.Tensor([0.0, 0.0, 0.0])
        elif viewpoints_count == 4:
            # front, top, right, bottom
            azim = torch.Tensor([0.0, 0.0, math.pi / 2.0, 0.0])
            elev = torch.Tensor([0.0, math.pi / 2.0 - 0.01, 0.0, -math.pi / 2.0 + 0.01])
            theta = torch.Tensor([0.0, 0.0, 0.0, 0.0])
        else:
            viewpoints_count_sqrt = math.ceil(math.sqrt(viewpoints_count))
            range_max = 1.0 - 1.0 / viewpoints_count_sqrt
            azim = torch.linspace(
                -math.pi * range_max,
                math.pi * range_max,
                viewpoints_count_sqrt,
            )
            elev = torch.linspace(
                +math.pi / 2.0 * range_max,
                -math.pi / 2.0 * range_max,
                viewpoints_count_sqrt,
            )
            azim = azim.repeat(viewpoints_count_sqrt)[:viewpoints_count]
            elev = elev.repeat_interleave(viewpoints_count_sqrt)[:viewpoints_count]
            theta = torch.zeros_like(elev)
    else:
        azim = torch.linspace(-math.pi, math.pi, viewpoints_count)
        viewpoints_count_first = viewpoints_count // 2
        viewpoints_count_second = viewpoints_count - viewpoints_count_first
        elev = torch.cat(
            [
                torch.linspace(
                    -math.pi / 2 * 0.1,
                    math.pi / 2 * 0.4,
                    viewpoints_count_first,
                ),
                torch.linspace(
                    math.pi / 2 * 0.4,
                    -math.pi / 2 * 0.1,
                    viewpoints_count_second,
                ),
            ],
            dim=0,
        )
        elev = elev
        theta = torch.zeros_like(elev)

    if dist == 0.0:
        cam_tform4x4_obj = transf4x4_from_spherical(
            azim=azim,
            elev=elev,
            theta=theta,
            dist=1.0,
        )
        cam_tform4x4_obj[:, :3, 3] = 0.0
    else:
        cam_tform4x4_obj = transf4x4_from_spherical(
            azim=azim,
            elev=elev,
            theta=theta,
            dist=dist,
        )

    if dtype is not None:
        cam_tform4x4_obj = cam_tform4x4_obj.to(dtype=dtype)

    if device is not None:
        cam_tform4x4_obj = cam_tform4x4_obj.to(device=device)

    return cam_tform4x4_obj


def transf4x4_from_spherical(azim, elev, theta, dist):
    # camera center
    obj_transl3_cam = torch.stack(
        [
            dist * torch.cos(elev) * torch.sin(azim),
            -dist * torch.cos(elev) * torch.cos(azim),
            dist * torch.sin(elev),
        ],
        dim=-1,
    )

    return transf4x4_from_pos_and_theta(obj_transl3_cam, theta)


def rot3x3_from_yaw_pitch(yaw, pitch, roll):
    # convention A
    rotation_matrix = torch.Tensor(
        [
            [
                math.cos(yaw) * math.cos(pitch),
                math.cos(yaw) * math.sin(pitch) * math.sin(roll)
                - math.sin(yaw) * math.cos(roll),
                math.cos(yaw) * math.sin(pitch) * math.cos(roll)
                + math.sin(yaw) * math.sin(roll),
            ],
            [
                math.sin(yaw) * math.cos(pitch),
                math.sin(yaw) * math.sin(pitch) * math.sin(roll)
                + math.cos(yaw) * math.cos(roll),
                math.sin(yaw) * math.sin(pitch) * math.cos(roll)
                - math.cos(yaw) * math.sin(roll),
            ],
            [
                -math.sin(pitch),
                math.cos(pitch) * math.sin(roll),
                math.cos(pitch) * math.cos(roll),
            ],
        ],
    )

    # convention B
    rotation_matrix = torch.Tensor(
        [
            [
                math.cos(pitch) * math.cos(yaw),
                math.cos(pitch) * math.sin(yaw),
                -math.sin(pitch),
            ],
            [
                math.sin(roll) * math.sin(pitch) * math.cos(yaw)
                - math.cos(roll) * math.sin(yaw),
                math.sin(roll) * math.sin(pitch) * math.sin(yaw)
                + math.cos(roll) * math.cos(yaw),
                math.sin(roll) * math.cos(pitch),
            ],
            [
                math.cos(roll) * math.sin(pitch) * math.cos(yaw)
                + math.sin(roll) * math.sin(yaw),
                math.cos(roll) * math.sin(pitch) * math.sin(yaw)
                - math.sin(roll) * math.cos(yaw),
                math.cos(roll) * math.cos(pitch),
            ],
        ],
    )
    return rotation_matrix


import numpy as np
from scipy.spatial.transform import Rotation as R


def get_ico_traj_cam_tform4x4_obj_for_viewpoints_count(
    viewpoints_count=100,
    radius=1,
    theta_count=1,
    geodesic_distance=0.3,
    real=False,
):
    """
    Generate n points along a random geodesic trajectory on a unit sphere,
    ensuring the endpoints are separated by a given geodesic distance.

    Parameters:
        viewpoints_count (int): Number of points to generate.
        radius (float): Radius of the sphere (default is 1).
        geodesic_distance (float): Geodesic distance between the first and last point.

    Returns:
        np.ndarray: (n, 3) array of points on the sphere.
    """
    # Choose a random starting point on the sphere
    u, v = np.random.uniform(0, 1, 2)
    theta1 = 2 * np.pi * u  # Azimuthal angle

    if real:
        # range: 0:1 -> 0.5:0.75
        v = (v / 4) + 0.5
        phi1 = np.arccos(2 * v - 1)  # Polar angle
    else:
        phi1 = np.arccos(2 * v - 1)  # Polar angle

    p1 = np.array(
        [
            np.sin(phi1) * np.cos(theta1),
            np.sin(phi1) * np.sin(theta1),
            np.cos(phi1),
        ],
    )

    if real:
        random_vec = np.array([0, 0, 1])
    else:
        # Choose a random great-circle direction
        random_vec = np.random.randn(3)
        random_vec -= random_vec.dot(p1) * p1  # Ensure it's perpendicular to p1
        random_vec /= np.linalg.norm(random_vec)

    p1 *= radius

    # Compute the required rotation angle
    angle = geodesic_distance  # Assuming small angles (for a unit sphere, distance ~ angle in radians)

    # Generate n points along the great-circle path
    angles = np.linspace(0, angle, viewpoints_count)
    points = np.array([R.from_rotvec(a * random_vec).apply(p1) for a in angles])

    xyz = torch.from_numpy(points).to(dtype=torch.float)

    theta_offset = torch.linspace(
        0,
        2 * torch.pi - (2 * torch.pi) / theta_count,
        theta_count,
    )
    if real:
        theta_start = torch.rand(1) * 0.0
        theta_end = torch.rand(1) * 0.0
    else:
        theta_start = torch.rand(1) * 2 * torch.pi
        theta_end = torch.rand(1) * 2 * torch.pi

    theta = torch.linspace(float(theta_start), float(theta_end), viewpoints_count)
    # xyz : V x 3,
    # theta: V
    xyz = xyz.repeat_interleave(theta_count, dim=0)
    theta = theta.repeat_interleave(theta_count, dim=0)
    theta_offset = theta_offset.repeat(viewpoints_count)
    theta += theta_offset

    cam_tform4x4_obj = transf4x4_from_pos_and_theta(
        pos=xyz,
        theta=theta,
    )  # torch.zeros_like(xyz[:, 0]))

    return cam_tform4x4_obj


def get_ico_cam_tform4x4_obj_for_viewpoints_count(
    viewpoints_count=100,
    radius=1,
    theta_count=1,
    viewpoints_uniform=True,
    theta_uniform=True,
):
    if isinstance(radius, torch.Tensor):
        radius = radius.clone().detach().cpu()

    if viewpoints_uniform:
        # number views
        # import torch
        # import math
        N = viewpoints_count
        # radius
        r = radius
        # area sphere
        A = 4 * torch.pi * r**2
        # area single viewpoint
        A_single = A / N
        # radius single viewpoint
        r_single = torch.sqrt(torch.Tensor([A_single])).item() / 2
        # circumference sphere
        U = 2 * torch.pi * r
        # number elevation sections
        E = int((U / 2) / (2 * r_single) + 1)

        e = torch.linspace(-torch.pi / 2, torch.pi / 2, E)

        r_e = torch.cos(e.abs()).abs() * r
        N_e = (r_e / r_e.sum()) * N
        N_left = N

        for i in range(math.ceil(len(N_e) / 2.0)):
            N_e[i] = N_e[i].clamp(min=1).round().int()  # = N_e.clamp(min=1)
            N_e[-(i + 1)] = N_e[-(i + 1)].clamp(min=1).round().int()
            N_left -= N_e[i]
            N_left -= N_e[-(i + 1)]
            N_e[i + 1 : len(N_e) - i - 1] = (
                N_e[i + 1 : len(N_e) - i - 1]
                / (N_e[i + 1 : len(N_e) - i - 1].sum() + 1e-10)
            ) * N_left

        # azimuth per evalation
        a_per_e = []
        xyz = []
        for e_id, N_e_single in enumerate(N_e):
            a_per_e.append(
                torch.linspace(
                    0,
                    2 * torch.pi - (2 * torch.pi) / N_e_single.int(),
                    N_e_single.int(),
                ),
            )
            r_e = torch.cos(e[e_id].abs()).abs()
            x = torch.sin(a_per_e[-1]) * r_e
            y = torch.cos(a_per_e[-1]) * r_e
            z = torch.sin(e[e_id])
            _xyz = torch.stack([x, y, z[None,].repeat(len(x))], dim=-1)
            xyz.append(_xyz)

        xyz = torch.cat(xyz, dim=0)
    else:
        xyz = torch.rand((viewpoints_count, 3)) - 0.5
        xyz = xyz / xyz.norm(keepdim=True, dim=-1)

    xyz *= radius

    if theta_uniform:
        theta = torch.linspace(
            0,
            2 * torch.pi - (2 * torch.pi) / theta_count,
            theta_count,
        )
    else:
        theta = torch.rand(theta_count) * 2 * torch.pi
    # xyz : V x 3,
    # theta: T
    xyz = xyz.repeat_interleave(theta_count, dim=0)
    theta = theta.repeat(viewpoints_count)

    cam_tform4x4_obj = transf4x4_from_pos_and_theta(
        pos=xyz,
        theta=theta,
    )  # torch.zeros_like(xyz[:, 0]))

    return cam_tform4x4_obj
    # look_at_rotation()
    # from od3d.cv.visual.show import show_scene
    # show_scene(pts3d=[xyz])

    """

    cam_transl3_obj = -obj_transl3_cam

    azim = -azim
    elev = -(torch.pi / 2 - elev)

    # rotation matrix
    camazim_tform_cam = torch.stack([
        torch.cos(azim), -torch.sin(azim), zeros, torch.sin(azim), torch.cos(azim), zeros, zeros, zeros, ones
    ], dim=-1).reshape(-1, 3, 3) # .permute(2, 0, 1)

    camelev_tform_camazim = torch.stack([
        ones, zeros, zeros, zeros, torch.cos(elev), -torch.sin(elev), zeros, torch.sin(elev), torch.cos(elev)
    ], dim=-1).reshape(-1, 3, 3) # .permute(2, 0, 1)

    camtheta_tform_camelev = torch.stack([
        torch.cos(theta), -torch.sin(theta), zeros, torch.sin(theta), torch.cos(theta), zeros, zeros, zeros, ones
    ], dim=-1).reshape(-1, 3, 3) # .permute(2, 0, 1)

    camrot_rot3x3_cam = torch.bmm(camtheta_tform_camelev, torch.bmm(camelev_tform_camazim, camazim_tform_cam))

    camrot_transl3_obj = rot3d(pts3d=cam_transl3_obj, rot3x3=camrot_rot3x3_cam)

    camrot_tform4x4_obj = transf4x4_from_rot3x3_and_transl3(camrot_rot3x3_cam, camrot_transl3_obj)

    camrot_tform4x4_obj[:, 1:3, :] = -camrot_tform4x4_obj[:, 1:3, :]

    return camrot_tform4x4_obj

    """

    # camrot_tform_obj = np.hstack((camrot_tform_cam, np.dot(camrot_tform_cam, cam_transl3_obj)))
    # camrot_tform_obj = np.vstack((camrot_tform_obj, [0, 0, 0, 1]))

    # T =
    # dist, elev, azim
    # R, t = look_at_view_transform(dist, elev=elev_s, azim=azim_s, degrees=False)

    # return 0.


@torch.jit.script
def transf4x4_from_rot3x3(rot3x3):
    transf4x4 = torch.zeros(
        rot3x3.shape[:-2] + torch.Size([4, 4]),
        device=rot3x3.device,
        dtype=rot3x3.dtype,
    )
    transf4x4[..., :3, :3] = rot3x3
    transf4x4[..., 3, 3] = 1.0
    return transf4x4


def rot3x3_from_tform4x4(_tform4x4: torch.Tensor):
    return _tform4x4[..., :3, :3]


def transf4x4_from_rot4_and_transl3(rot4, transl3):
    """
    Args:
        rot4 (Union[torch.Tensor, List[float]]): ...x4, Quaternion with wxyz
        transl3 (torch.Tensor): ...x3
    Returns:
        tform4x4 (torch.Tensor): ...x4x4
    """

    from kornia.geometry.quaternion import Quaternion
    import torch

    cam_rotQ_world = Quaternion.from_coeffs(
        w=float(rot4[0]),
        x=float(rot4[1]),
        y=float(rot4[2]),
        z=float(rot4[3]),
    )
    if isinstance(transl3, list):
        transl3 = torch.FloatTensor(transl3)

    cam_tform4x4_world = transf4x4_from_rot3x3_and_transl3(
        rot3x3=cam_rotQ_world.matrix(),
        transl3=transl3,
    )

    return cam_tform4x4_world


@torch.jit.script
def transf4x4_from_rot3x3_and_transl3(rot3x3, transl3):
    transf4x4 = transf4x4_from_rot3x3(rot3x3)
    transf4x4[..., :3, 3] = transl3
    return transf4x4


def tform4x4_from_transl3d(transl3d: torch.Tensor):
    """
    Args:
        transl3d (torch.Tensor): ...x3
    Returns:
        tform4x4 (torch.Tensor): ...x4x4
    """
    a_tform4x4_b = (
        torch.eye(4)[(None,) * (len(transl3d.shape) - 1)]
        .expand(transl3d.shape[:-1] + torch.Size([4, 4]))
        .to(device=transl3d.device, dtype=transl3d.dtype)
    )
    a_tform4x4_b[..., :3, 3] = transl3d
    return a_tform4x4_b

def transl3d_from_tform4x4(tform4x4: torch.Tensor):
    """
    Args:
        tform4x4 (torch.Tensor): ...x4x4
    Returns:
        transl3d (torch.Tensor): ...x3
    """
    transl3d = tform4x4[..., :3, 3].clone()
    return transl3d

def rot2d(pts2d, rot2x2):
    pts2d_shape_in = pts2d.shape
    pts2d_rot = torch.bmm(rot2x2.reshape(-1, 2, 2), pts2d.reshape(-1, 2, 1)).reshape(
        pts2d_shape_in,
    )
    return pts2d_rot


@torch.jit.script
def rot3d(pts3d, rot3x3):
    pts3d_shape_in = pts3d.shape
    pts3d_rot = torch.bmm(rot3x3.reshape(-1, 3, 3), pts3d.reshape(-1, 3, 1)).reshape(
        pts3d_shape_in,
    )
    return pts3d_rot


def rot3d_broadcast(pts3d, rot3x3):
    shape_first_dims = torch.broadcast_shapes(pts3d.shape[:-1], rot3x3.shape[:-2])
    return rot3d(
        pts3d.expand(*shape_first_dims, 3),
        rot3x3.expand(*shape_first_dims, 3, 3),
    )


def proj3d2d_broadcast(pts3d, proj4x4):
    shape_first_dims = torch.broadcast_shapes(pts3d.shape[:-1], proj4x4.shape[:-2])
    return proj3d2d(
        pts3d.expand(*shape_first_dims, 3),
        proj4x4.expand(*shape_first_dims, 4, 4),
    )


def pts3d_to_pts4d(pts3d):
    device = pts3d.device
    dtype = pts3d.dtype
    ones1d = torch.ones(size=list(pts3d.shape[:-1]) + [1]).to(
        device=device,
        dtype=dtype,
    )
    pts4d = torch.concatenate([pts3d, ones1d], dim=-1)
    return pts4d


def pts2d_to_pts3d(pts2d):
    device = pts2d.device
    dtype = pts2d.dtype
    ones1d = torch.ones(size=list(pts2d.shape[:-1]) + [1]).to(
        device=device,
        dtype=dtype,
    )
    pts3d = torch.concatenate([pts2d, ones1d], dim=-1)
    return pts3d


def pts2d_to_pts4d(pts2d):
    device = pts2d.device
    dtype = pts2d.dtype
    ones2d = torch.ones(size=list(pts2d.shape[:-1]) + [2]).to(
        device=device,
        dtype=dtype,
    )
    pts4d = torch.concatenate([pts2d, ones2d], dim=-1)
    pts4d = pts4d.reshape(list(pts4d.shape) + [1])
    return pts4d


def proj3d2d_origin(proj4x4):
    device = proj4x4.device
    dtype = proj4x4.dtype
    pts3d = torch.zeros(
        size=proj4x4.shape[:-2] + torch.Size([3]),
        device=device,
        dtype=dtype,
    )
    return proj3d2d(pts3d=pts3d, proj4x4=proj4x4)


def add_homog_dim(pts, dim):
    device = pts.device
    dtype = pts.dtype
    if dim == -1:
        dim = pts.dim() - 1
    ones1d = torch.ones(
        size=list(pts.shape[:dim]) + [1] + list(pts.shape[dim + 1 :]),
    ).to(device=device, dtype=dtype)
    return torch.cat([pts, ones1d], dim=dim)


def proj3d2d(pts3d, proj4x4):
    device = pts3d.device
    dtype = pts3d.dtype
    ones1d = torch.ones(size=list(pts3d.shape[:-1]) + [1]).to(
        device=device,
        dtype=dtype,
    )
    pts4d = torch.concatenate([pts3d, ones1d], dim=-1)
    pts4d = pts4d.reshape(list(pts4d.shape) + [1])
    pts4d_transf = torch.bmm(
        proj4x4.reshape(-1, 4, 4),
        pts4d.reshape(-1, 4, 1),
    ).reshape(pts4d.shape)
    dim_coords3d = pts4d_transf.dim() - 2
    pts3d_transf = pts4d_transf.index_select(
        dim=dim_coords3d,
        index=torch.LongTensor([0, 1, 2]).to(device=device),
    )
    pts2d_transf = pts3d_transf.index_select(
        dim=dim_coords3d,
        index=torch.LongTensor([0, 1]).to(device=device),
    )
    ptsZ_transf = pts3d_transf.index_select(
        dim=dim_coords3d,
        index=torch.LongTensor([2]).to(device=device),
    )
    pts2d_transf_proj = pts2d_transf / (ptsZ_transf.abs() + 1e-10)
    pts2d_transf_proj = pts2d_transf_proj.squeeze(dim=-1)
    return pts2d_transf_proj


def reproj2d3d_broadcast(pxl2d, proj4x4_inv):
    shape_first_dims = torch.broadcast_shapes(pxl2d.shape[:-1], proj4x4_inv.shape[:-2])
    return reproj2d3d(
        pxl2d.expand(*shape_first_dims, 2),
        proj4x4_inv.expand(*shape_first_dims, 4, 4),
    )


def reproj2d3d(pxl2d, proj4x4_inv):
    device = pxl2d.device
    pts4d = pts2d_to_pts4d(pxl2d)
    pts4d_reproj = torch.bmm(
        proj4x4_inv.reshape(-1, 4, 4),
        pts4d.reshape(-1, 4, 1),
    ).reshape(pts4d.shape)
    dim_coords2d = pts4d_reproj.dim() - 2
    pts3d_reproj = pts4d_reproj.index_select(
        dim=dim_coords2d,
        index=torch.LongTensor([0, 1, 2]).to(device=device),
    )
    pts3d_reproj = pts3d_reproj.squeeze(dim=-1)
    return pts3d_reproj


def cam_intr4x4_downsample(cams_intr4x4=None, imgs_sizes=None, down_sample_rate=1.0):
    """
    Render the objects in the scene with the given camera parameters.
    Args:
        cams_tform4x4_obj: (B, C, 4, 4) or (B, 4, 4) tensor of camera poses in the object frame.
        cams_intr4x4: (4, 4), or (B, 4, 4) or (B, C, 4, 4) tensor of camera intrinsics.
        imgs_sizes: (2,) tensor of (H, W)
    Returns:
        cams_intr4x4: (4, 4), or (B, 4, 4) or (B, C, 4, 4) tensor of camera intrinsics.
        imgs_sizes: (2,) tensor of (H, W)
    """
    if down_sample_rate != 1.0:
        if cams_intr4x4 is not None:
            cams_intr4x4 = cams_intr4x4.clone()
            if cams_intr4x4.dim() == 2:
                cams_intr4x4[:2] /= down_sample_rate
            elif cams_intr4x4.dim() == 3:
                cams_intr4x4[:, :2] /= down_sample_rate
            elif cams_intr4x4.dim() == 4:
                cams_intr4x4[:, :, :2] /= down_sample_rate
            else:
                raise NotImplementedError

        if imgs_sizes is not None:
            if isinstance(imgs_sizes, torch.Size):
                imgs_sizes = torch.LongTensor(list(imgs_sizes))
            imgs_sizes = imgs_sizes.clone() // down_sample_rate
    else:
        if cams_intr4x4 is not None:
            cams_intr4x4 = cams_intr4x4.clone()
        if imgs_sizes is not None:
            if isinstance(imgs_sizes, torch.Size):
                imgs_sizes = torch.LongTensor(list(imgs_sizes))
            imgs_sizes = imgs_sizes.clone()
    return cams_intr4x4, imgs_sizes

def cam_transl3d_2_cam_transl_norm3d(cam_intr4x4, cam_transl3d, H, W):
    pxl2d = proj3d2d(pts3d=cam_transl3d, proj4x4=cam_intr4x4)
    pxl2d_norm = pxl2d.clone()
    pxl2d_norm
    pass

def cam_transl_norm3d_2_cam_transl3d(cam_intr4x4, cam_transl_norm3d):
    pass

def cam_intr4x4_2_rays3d(cam_intr4x4, size):
    #  depth: ...x1xHxW
    #  cam_intr: ...x4x4
    #  size: [H, W]
    H, W = size
    H = int(H)
    W = int(W)
    device = cam_intr4x4.device
    dtype = cam_intr4x4.dtype
    pxl2d = torch.stack(
        torch.meshgrid(torch.arange(W), torch.arange(H), indexing="xy"),
        dim=-1,
    ).to(device=device, dtype=dtype)
    # pxl2d[(None, ) * (cam_intr4x4.dim() - 2)] # legacy code, do not use for not broadcasting cam intr...
    pts3d_homog = (
        reproj2d3d_broadcast(
            pxl2d,
            proj4x4_inv=cam_intr4x4[..., None, None, :, :].inverse(),
        )
        .transpose(-2, -1)
        .transpose(-3, -2)
    )
    shape_first_dims = torch.broadcast_shapes(cam_intr4x4.shape[:-2])
    pts3d = pts3d_homog.expand(*shape_first_dims, 3, H, W)

    pts3d = torch.nn.functional.normalize(pts3d, dim=-3)
    return pts3d


def depth2pts3d_grid(depth, cam_intr4x4):
    #  depth: ...x1xHxW
    #  cam_intr: ...x4x4
    device = cam_intr4x4.device
    dtype = cam_intr4x4.dtype
    H, W = depth.shape[-2:]
    pxl2d = torch.stack(
        torch.meshgrid(torch.arange(W), torch.arange(H), indexing="xy"),
        dim=-1,
    ).to(device=device, dtype=dtype)
    # pxl2d[(None, ) * (cam_intr4x4.dim() - 2)] # legacy code, do not use for not broadcasting cam intr...
    pts3d_homog = (
        reproj2d3d_broadcast(
            pxl2d,
            proj4x4_inv=cam_intr4x4[..., None, None, :, :].inverse(),
        )
        .transpose(-2, -1)
        .transpose(-3, -2)
    )
    shape_first_dims = torch.broadcast_shapes(depth.shape[:-3], cam_intr4x4.shape[:-2])
    pts3d = pts3d_homog.expand(*shape_first_dims, 3, H, W) * depth.expand(
        *shape_first_dims,
        1,
        H,
        W,
    )
    return pts3d


def cam_intr4x4_to_cam_intr_ncds4x4(cam_intr4x4, size):
    cam_intr4x4_ncds = torch.zeros_like(cam_intr4x4)

    H, W = size
    s = 2 / min(H, W)
    f = cam_intr4x4[..., 0, 0]
    cam_intr4x4_ncds[..., 0, 0] = cam_intr4x4[..., 0, 0] * s
    cam_intr4x4_ncds[..., 0, 2] = -(cam_intr4x4[..., 0, 2] - W / 2) * s
    cam_intr4x4_ncds[..., 1, 1] = cam_intr4x4[..., 1, 1] * s
    cam_intr4x4_ncds[..., 1, 2] = -(cam_intr4x4[..., 1, 2] - H / 2) * s
    cam_intr4x4_ncds[..., 2, 2] = f * s
    cam_intr4x4_ncds[..., 3, 3] = 1.0
    return cam_intr4x4_ncds


def inv_cam_intr4x4(cam_intr4x4):
    cam_intr4x4_inv = torch.zeros_like(cam_intr4x4)
    fx = cam_intr4x4[..., 0, 0]
    fy = cam_intr4x4[..., 1, 1]
    px = cam_intr4x4[..., 0, 2]
    py = cam_intr4x4[..., 1, 2]
    s = cam_intr4x4[..., 2, 2]
    cam_intr4x4_inv[..., 0, 0] = 1.0 / fx
    cam_intr4x4_inv[..., 1, 1] = 1.0 / fy
    cam_intr4x4_inv[..., 0, 2] = -px / (fx * s)
    cam_intr4x4_inv[..., 1, 2] = -py / (fy * s)
    cam_intr4x4_inv[..., 2, 2] = 1.0 / s
    cam_intr4x4_inv[..., 3, 3] = 1.0
    return cam_intr4x4_inv


"""
K = [[fx,  0, px],
     [ 0, fy, py],
     [ 0,  0,  s]]
K^(-1) = [[fy*s,    0, -fy*px],
          [   0, fx*s, -fx*py],
          [   0,    0,  fx*fy]] * 1 / (fx*fy*s)

K^(-1) = [[1/fx,    0, -px/(fx*s)],
          [   0, 1/fy, -py/(fy*s)],
          [   0,    0,  1/s]]

K_ncds^(-1) = [[1/(fx*s),        0, (px-W/2)/(fx*s)],
               [       0, 1/(fy*s), (py-H/2)/(fy*s)],
               [       0,        0,  1/(fx*s)]]
"""

from od3d.cv.differentiation.gradient import calc_batch_gradients


def depth2normals_grid(depth, cam_intr4x4, shift=1):
    # depth: ...x1xHxW
    # cam_intr: ...x4x4
    device = depth.device
    dtype = depth.dtype

    fx = cam_intr4x4[..., 0, 0]
    fy = cam_intr4x4[..., 1, 1]

    dz_dpx, dz_dpy = calc_batch_gradients(depth, pad_zeros=True, shift=shift)
    dpx_dx = fx[..., None, None, None] / (shift * depth)
    dpy_dy = fy[..., None, None, None] / (shift * depth)
    dz_dx = dz_dpx * dpx_dx
    dz_dy = dz_dpy * dpy_dy
    dz_dx = dz_dx.nan_to_num(0.0, neginf=0.0, posinf=0.0)
    dz_dy = dz_dy.nan_to_num(0.0, neginf=0.0, posinf=0.0)
    normals = torch.zeros(size=depth.shape[:-3] + (3,) + depth.shape[-2:]).to(
        dtype=dtype,
        device=device,
    )
    normals[..., 2, :, :] = -1.0
    normals[..., 0:1, :, :] = dz_dx
    normals[..., 1:2, :, :] = dz_dy
    normals = torch.nn.functional.normalize(normals, dim=-3)
    return normals

    # pxl2d = torch.stack(torch.meshgrid(torch.arange(W), torch.arange(H), indexing='xy'), dim=-1).to(device=device, dtype=dtype)
    # # pxl2d[(None, ) * (cam_intr4x4.dim() - 2)] # legacy code, do not use for not broadcasting cam intr...
    # pts3d_homog = reproj2d3d_broadcast(pxl2d, proj4x4_inv=cam_intr4x4[..., None, None, :, :].inverse()).transpose(-2, -1).transpose(-3, -2)
    # shape_first_dims = torch.broadcast_shapes(depth.shape[:-3], cam_intr4x4.shape[:-2])
    # pts3d = pts3d_homog.expand(*shape_first_dims, 3, H, W) * depth.expand(*shape_first_dims, 1, H, W)
    # return pts3d


def transf3d_normal_broadcast(normals3d, transf4x4):
    shape_first_dims = torch.broadcast_shapes(
        normals3d.shape[:-1],
        transf4x4.shape[:-2],
    )
    transf4x4_zero_transl = transf4x4.clone()
    transf4x4_zero_transl[..., :3, 3] = 0.0
    return transf3d(
        normals3d.expand(*shape_first_dims, 3),
        transf4x4_zero_transl.expand(*shape_first_dims, 4, 4),
    )


def transf3d_broadcast(pts3d, transf4x4):
    shape_first_dims = torch.broadcast_shapes(pts3d.shape[:-1], transf4x4.shape[:-2])
    return transf3d(
        pts3d.expand(*shape_first_dims, 3),
        transf4x4.expand(*shape_first_dims, 4, 4),
    )


def cam_intr_to_4x4(fx, fy, cx, cy):
    """
    Args:
        fx: (float)
        fy: (float)
        cx: (float)
        cy: (float)
    Returns:
        cam_intr_4x4: 4x4, [[fx, 0, cx, 0], [0, fy, cy, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    """

    return cam_intr_4_to_4x4(torch.FloatTensor([fx, fy, cx, cy]))


def cam_intr_4_to_4x4(cam_intr4):
    """
    Args:
        cam_intr4: ...x4, [fx, fy, cx, cy]
    Returns:
        cam_intr_4x4: ...x4x4, [[fx, 0, cx, 0], [0, fy, cy, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    """
    cam_intr4x4 = torch.eye(4).expand(cam_intr4.shape[:-1] + (4, 4)).clone()
    cam_intr4x4[..., 0, 0] = cam_intr4[..., 0]
    cam_intr4x4[..., 1, 1] = cam_intr4[..., 1]
    cam_intr4x4[..., 0, 2] = cam_intr4[..., 2]
    cam_intr4x4[..., 1, 2] = cam_intr4[..., 3]
    return cam_intr4x4


def transf3d(pts3d, transf4x4):
    """
    Args:
        pts3d (torch.Tensor): ...x3
        transf4x4 (torch.Tensor): ...x4x4

    Returns:
        pts3d_transf (torch.Tensor): ...x3
    """
    device = pts3d.device
    dtype = pts3d.dtype
    transf4x4 = transf4x4.to(device)
    ones1d = torch.ones(size=list(pts3d.shape[:-1]) + [1]).to(
        device=device,
        dtype=dtype,
    )
    pts4d = torch.concatenate([pts3d, ones1d], dim=-1)
    pts4d = pts4d.reshape(list(pts4d.shape) + [1])
    pts4d_transf = torch.bmm(
        transf4x4.reshape(-1, 4, 4),
        pts4d.reshape(-1, 4, 1),
    ).reshape(pts4d.shape)
    dim_coords3d = pts4d_transf.dim() - 2
    pts3d_transf = pts4d_transf.index_select(
        dim=dim_coords3d,
        index=torch.LongTensor([0, 1, 2]).to(device=device),
    )
    pts3d_transf = pts3d_transf.squeeze(dim=-1)
    return pts3d_transf


def transf2d(pts2d, transf3x3):
    """
    Args:
        pts2d (torch.Tensor): ...x2
        transf3x3 (torch.Tensor): ...x3x3

    Returns:
        pts2d_transf (torch.Tensor): ...x2
    """
    device = pts2d.device
    dtype = pts2d.dtype
    ones1d = torch.ones(size=list(pts2d.shape[:-1]) + [1]).to(
        device=device,
        dtype=dtype,
    )
    pts3d = torch.concatenate([pts2d, ones1d], dim=-1)
    pts3d = pts3d.reshape(list(pts3d.shape) + [1])
    pts2d_transf = torch.bmm(
        transf3x3.reshape(-1, 3, 3),
        pts3d.reshape(-1, 3, 1),
    ).reshape(pts3d.shape)
    dim_coords2d = pts2d_transf.dim() - 2
    pts2d_transf = pts2d_transf.index_select(
        dim=dim_coords2d,
        index=torch.LongTensor([0, 1]).to(device=device),
    )
    pts2d_transf = pts2d_transf.squeeze(dim=-1)
    return pts2d_transf


def plane4d_to_tform4x4(plane4d: torch.Tensor):
    """
    Args:
        plane4d (torch.Tensor): ...x4, first 3 dimensions are axis, last dimension offset.
    Returns:
        plan3d_tform_pts (torch.Tensor): ...x4x4

    """
    device = plane4d.device
    plane3d_tform4x4_obj = torch.eye(4).to(device=device)
    top_axis = plane4d[:3] / plane4d[:3].norm()
    x = top_axis[0]
    y = top_axis[1]
    z = top_axis[2]
    if x != 0 or y != 0:
        left_axis = torch.Tensor([-y, x, 0.0]).to(device=device)
        left_axis = left_axis / left_axis.norm()
        back_axis = torch.Tensor([-x * z, -y * z, x * x + y * y]).to(device=device)
        back_axis = back_axis / back_axis.norm()
    else:
        left_axis = torch.Tensor([1.0, 0.0, 0.0], device=device)
        back_axis = torch.Tensor([0.0, 1.0, 0.0], device=device)
    plane3d_tform4x4_obj[0, :3] = left_axis
    plane3d_tform4x4_obj[1, :3] = back_axis
    plane3d_tform4x4_obj[2, :3] = top_axis
    plane3d_tform4x4_obj[2, 3] = -plane4d[3]

    return plane3d_tform4x4_obj
