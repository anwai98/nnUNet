from batchgenerators.augmentations.utils import create_zero_centered_coordinate_mesh, elastic_deform_coordinates, \
    rotate_coords_3d, rotate_coords_2d, scale_coords, interpolate_img
from batchgenerators.transforms.abstract_transforms import AbstractTransform

from nnunet.training.network_training.diag.transforms.crop_and_pad_augmentations import random_crop as random_crop_aug
from nnunet.training.network_training.diag.transforms.crop_and_pad_augmentations import center_crop as center_crop_aug


import numpy as np


class SpatialTransformWithWeights(AbstractTransform):
    """The ultimate spatial transform generator. Rotation, deformation, scaling, cropping: It has all you ever dreamed
    of. Computational time scales only with patch_size, not with input patch size or type of augmentations used.
    Internally, this transform will use a coordinate grid of shape patch_size to which the transformations are
    applied (very fast). Interpolation on the image data will only be done at the very end

    Args:
        patch_size (tuple/list/ndarray of int): Output patch size

        patch_center_dist_from_border (tuple/list/ndarray of int, or int): How far should the center pixel of the
        extracted patch be from the image border? Recommended to use patch_size//2.
        This only applies when random_crop=True

        do_elastic_deform (bool): Whether or not to apply elastic deformation

        alpha (tuple of float): magnitude of the elastic deformation; randomly sampled from interval

        sigma (tuple of float): scale of the elastic deformation (small = local, large = global); randomly sampled
        from interval

        do_rotation (bool): Whether or not to apply rotation

        angle_x, angle_y, angle_z (tuple of float): angle in rad; randomly sampled from interval. Always double check
        whether axes are correct!

        do_scale (bool): Whether or not to apply scaling

        scale (tuple of float): scale range ; scale is randomly sampled from interval

        border_mode_data: How to treat border pixels in data? see scipy.ndimage.map_coordinates

        border_cval_data: If border_mode_data=constant, what value to use?

        order_data: Order of interpolation for data. see scipy.ndimage.map_coordinates

        border_mode_seg: How to treat border pixels in seg? see scipy.ndimage.map_coordinates

        border_cval_seg: If border_mode_seg=constant, what value to use?

        order_seg: Order of interpolation for seg. see scipy.ndimage.map_coordinates. Strongly recommended to use 0!
        If !=0 then you will have to round to int and also beware of interpolation artifacts if you have more then
        labels 0 and 1. (for example if you have [0, 0, 0, 2, 2, 1, 0] the neighboring [0, 0, 2] bay result in [0, 1, 2])

        random_crop: True: do a random crop of size patch_size and minimal distance to border of
        patch_center_dist_from_border. False: do a center crop of size patch_size

        independent_scale_for_each_axis: If True, a scale factor will be chosen independently for each axis.
    """

    def __init__(self, patch_size, patch_center_dist_from_border=30,
                 do_elastic_deform=True, alpha=(0., 1000.), sigma=(10., 13.),
                 do_rotation=True, angle_x=(0, 2 * np.pi), angle_y=(0, 2 * np.pi), angle_z=(0, 2 * np.pi),
                 do_scale=True, scale=(0.75, 1.25), border_mode_data='nearest', border_cval_data=0, order_data=3,
                 border_mode_seg='constant', border_cval_seg=0, order_seg=0,
                 border_mode_weightmap='constant', border_cval_weightmap=0, order_weightmap=1,
                 random_crop=True, data_key="data",
                 label_key="seg", weightmap_key="weightmap", p_el_per_sample=1, p_scale_per_sample=1, p_rot_per_sample=1,
                 independent_scale_for_each_axis=False, p_rot_per_axis:float=1, p_independent_scale_per_axis: int=1):
        self.independent_scale_for_each_axis = independent_scale_for_each_axis
        self.p_rot_per_sample = p_rot_per_sample
        self.p_scale_per_sample = p_scale_per_sample
        self.p_el_per_sample = p_el_per_sample
        self.data_key = data_key
        self.label_key = label_key
        self.weightmap_key = weightmap_key
        self.patch_size = patch_size
        self.patch_center_dist_from_border = patch_center_dist_from_border
        self.do_elastic_deform = do_elastic_deform
        self.alpha = alpha
        self.sigma = sigma
        self.do_rotation = do_rotation
        self.angle_x = angle_x
        self.angle_y = angle_y
        self.angle_z = angle_z
        self.do_scale = do_scale
        self.scale = scale
        self.border_mode_data = border_mode_data
        self.border_cval_data = border_cval_data
        self.order_data = order_data
        self.border_mode_seg = border_mode_seg
        self.border_cval_seg = border_cval_seg
        self.order_seg = order_seg
        self.border_mode_weightmap = border_mode_weightmap
        self.border_cval_weightmap = border_cval_weightmap
        self.order_weightmap = order_weightmap
        self.random_crop = random_crop
        self.p_rot_per_axis = p_rot_per_axis
        self.p_independent_scale_per_axis = p_independent_scale_per_axis

    def __call__(self, **data_dict):
        data = data_dict.get(self.data_key)
        seg = data_dict.get(self.label_key)
        weightmap = data_dict.get(self.weightmap_key)

        if self.patch_size is None:
            if len(data.shape) == 4:
                patch_size = (data.shape[2], data.shape[3])
            elif len(data.shape) == 5:
                patch_size = (data.shape[2], data.shape[3], data.shape[4])
            else:
                raise ValueError("only support 2D/3D batch data.")
        else:
            patch_size = self.patch_size

        ret_val = augment_spatial(data, seg, weightmap, patch_size=patch_size,
                                  patch_center_dist_from_border=self.patch_center_dist_from_border,
                                  do_elastic_deform=self.do_elastic_deform, alpha=self.alpha, sigma=self.sigma,
                                  do_rotation=self.do_rotation, angle_x=self.angle_x, angle_y=self.angle_y,
                                  angle_z=self.angle_z, do_scale=self.do_scale, scale=self.scale,
                                  border_mode_data=self.border_mode_data,
                                  border_cval_data=self.border_cval_data, order_data=self.order_data,
                                  border_mode_seg=self.border_mode_seg, border_cval_seg=self.border_cval_seg,
                                  order_seg=self.order_seg,
                                  border_mode_weightmap=self.border_mode_weightmap, border_cval_weightmap=self.border_cval_weightmap,
                                  order_weightmap=self.order_weightmap,
                                  random_crop=self.random_crop,
                                  p_el_per_sample=self.p_el_per_sample, p_scale_per_sample=self.p_scale_per_sample,
                                  p_rot_per_sample=self.p_rot_per_sample,
                                  independent_scale_for_each_axis=self.independent_scale_for_each_axis,
                                  p_rot_per_axis=self.p_rot_per_axis,
                                  p_independent_scale_per_axis=self.p_independent_scale_per_axis)
        data_dict[self.data_key] = ret_val[0]
        if seg is not None:
            data_dict[self.label_key] = ret_val[1]
        if weightmap is not None:
            data_dict[self.weightmap_key] = ret_val[2]
        return data_dict


def augment_spatial(data, seg, weightmap, patch_size, patch_center_dist_from_border=30,
                    do_elastic_deform=True, alpha=(0., 1000.), sigma=(10., 13.),
                    do_rotation=True, angle_x=(0, 2 * np.pi), angle_y=(0, 2 * np.pi), angle_z=(0, 2 * np.pi),
                    do_scale=True, scale=(0.75, 1.25), border_mode_data='nearest', border_cval_data=0, order_data=3,
                    border_mode_seg='constant', border_cval_seg=0, order_seg=0,
                    border_mode_weightmap='constant', border_cval_weightmap=0, order_weightmap=1,
                    random_crop=True, p_el_per_sample=1,
                    p_scale_per_sample=1, p_rot_per_sample=1, independent_scale_for_each_axis=False,
                    p_rot_per_axis: float = 1, p_independent_scale_per_axis: int = 1):
    dim = len(patch_size)
    seg_result = None
    weightmap_result = None
    if seg is not None:
        if dim == 2:
            seg_result = np.zeros((seg.shape[0], seg.shape[1], patch_size[0], patch_size[1]), dtype=np.float32)
        else:
            seg_result = np.zeros((seg.shape[0], seg.shape[1], patch_size[0], patch_size[1], patch_size[2]),
                                  dtype=np.float32)
    if weightmap is not None:
        if dim == 2:
            weightmap_result = np.zeros((weightmap.shape[0], weightmap.shape[1], patch_size[0], patch_size[1]), dtype=np.float32)
        else:
            weightmap_result = np.zeros((weightmap.shape[0], weightmap.shape[1], patch_size[0], patch_size[1], patch_size[2]),
                                  dtype=np.float32)

    if dim == 2:
        data_result = np.zeros((data.shape[0], data.shape[1], patch_size[0], patch_size[1]), dtype=np.float32)
    else:
        data_result = np.zeros((data.shape[0], data.shape[1], patch_size[0], patch_size[1], patch_size[2]),
                               dtype=np.float32)

    if not isinstance(patch_center_dist_from_border, (list, tuple, np.ndarray)):
        patch_center_dist_from_border = dim * [patch_center_dist_from_border]

    for sample_id in range(data.shape[0]):
        coords = create_zero_centered_coordinate_mesh(patch_size)
        modified_coords = False

        if do_elastic_deform and np.random.uniform() < p_el_per_sample:
            a = np.random.uniform(alpha[0], alpha[1])
            s = np.random.uniform(sigma[0], sigma[1])
            coords = elastic_deform_coordinates(coords, a, s)
            modified_coords = True

        if do_rotation and np.random.uniform() < p_rot_per_sample:

            if np.random.uniform() <= p_rot_per_axis:
                a_x = np.random.uniform(angle_x[0], angle_x[1])
            else:
                a_x = 0

            if dim == 3:
                if np.random.uniform() <= p_rot_per_axis:
                    a_y = np.random.uniform(angle_y[0], angle_y[1])
                else:
                    a_y = 0

                if np.random.uniform() <= p_rot_per_axis:
                    a_z = np.random.uniform(angle_z[0], angle_z[1])
                else:
                    a_z = 0

                coords = rotate_coords_3d(coords, a_x, a_y, a_z)
            else:
                coords = rotate_coords_2d(coords, a_x)
            modified_coords = True

        if do_scale and np.random.uniform() < p_scale_per_sample:
            if independent_scale_for_each_axis and np.random.uniform() < p_independent_scale_per_axis:
                sc = []
                for _ in range(dim):
                    if np.random.random() < 0.5 and scale[0] < 1:
                        sc.append(np.random.uniform(scale[0], 1))
                    else:
                        sc.append(np.random.uniform(max(scale[0], 1), scale[1]))
            else:
                if np.random.random() < 0.5 and scale[0] < 1:
                    sc = np.random.uniform(scale[0], 1)
                else:
                    sc = np.random.uniform(max(scale[0], 1), scale[1])

            coords = scale_coords(coords, sc)
            modified_coords = True

        # now find a nice center location
        if modified_coords:
            for d in range(dim):
                if random_crop:
                    ctr = np.random.uniform(patch_center_dist_from_border[d],
                                            data.shape[d + 2] - patch_center_dist_from_border[d])
                else:
                    ctr = data.shape[d + 2] / 2. - 0.5
                coords[d] += ctr
            for channel_id in range(data.shape[1]):
                data_result[sample_id, channel_id] = interpolate_img(data[sample_id, channel_id], coords, order_data,
                                                                     border_mode_data, cval=border_cval_data)
            if seg is not None:
                for channel_id in range(seg.shape[1]):
                    seg_result[sample_id, channel_id] = interpolate_img(seg[sample_id, channel_id], coords, order_seg,
                                                                        border_mode_seg, cval=border_cval_seg,
                                                                        is_seg=True)
            if weightmap is not None:
                for channel_id in range(weightmap.shape[1]):
                    weightmap_result[sample_id, channel_id] = interpolate_img(weightmap[sample_id, channel_id], coords, order_weightmap,
                                                                        border_mode_weightmap, cval=border_cval_weightmap,
                                                                        is_seg=True)

        else:
            if seg is None:
                s = None
            else:
                s = seg[sample_id:sample_id + 1]
            if weightmap is None:
                w = None
            else:
                w = weightmap[sample_id:sample_id + 1]
            if random_crop:
                margin = [patch_center_dist_from_border[d] - patch_size[d] // 2 for d in range(dim)]
                d, s, w = random_crop_aug(data[sample_id:sample_id + 1], s, w, patch_size, margin)
            else:
                d, s, w = center_crop_aug(data[sample_id:sample_id + 1], patch_size, s, w)
            data_result[sample_id] = d[0]
            if seg is not None:
                seg_result[sample_id] = s[0]
            if weightmap is not None:
                weightmap_result[sample_id] = w[0]
    return data_result, seg_result, weightmap_result


class MirrorTransformWithWeights(AbstractTransform):
    """ Randomly mirrors data along specified axes. Mirroring is evenly distributed. Probability of mirroring along
    each axis is 0.5

    Args:
        axes (tuple of int): axes along which to mirror

    """

    def __init__(self, axes=(0, 1, 2), data_key="data", label_key="seg", weightmap_key="weightmap", p_per_sample=1):
        self.p_per_sample = p_per_sample
        self.data_key = data_key
        self.label_key = label_key
        self.weightmap_key = weightmap_key
        self.axes = axes
        if max(axes) > 2:
            raise ValueError("MirrorTransform now takes the axes as the spatial dimensions. What previously was "
                             "axes=(2, 3, 4) to mirror along all spatial dimensions of a 5d tensor (b, c, x, y, z) "
                             "is now axes=(0, 1, 2). Please adapt your scripts accordingly.")

    def __call__(self, **data_dict):
        data = data_dict.get(self.data_key)
        seg = data_dict.get(self.label_key)
        weightmap = data_dict.get(self.weightmap_key)

        for b in range(len(data)):
            if np.random.uniform() < self.p_per_sample:
                sample_seg = None
                if seg is not None:
                    sample_seg = seg[b]
                sample_weightmap = None
                if weightmap is not None:
                    sample_weightmap = weightmap[b]
                ret_val = augment_mirroring(
                    sample_data=data[b],
                    sample_seg=sample_seg,
                    sample_weightmap=sample_weightmap,
                    axes=self.axes
                )
                data[b] = ret_val[0]
                if seg is not None:
                    seg[b] = ret_val[1]
                if weightmap is not None:
                    weightmap[b] = ret_val[2]

        data_dict[self.data_key] = data
        if seg is not None:
            data_dict[self.label_key] = seg
        if weightmap is not None:
            data_dict[self.weightmap_key] = weightmap

        return data_dict


def augment_mirroring(sample_data, sample_seg=None, sample_weightmap=None, axes=(0, 1, 2)):
    if (len(sample_data.shape) != 3) and (len(sample_data.shape) != 4):
        raise Exception(
            "Invalid dimension for sample_data and sample_seg. sample_data and sample_seg should be either "
            "[channels, x, y] or [channels, x, y, z]")
    if 0 in axes and np.random.uniform() < 0.5:
        sample_data[:, :] = sample_data[:, ::-1]
        if sample_seg is not None:
            sample_seg[:, :] = sample_seg[:, ::-1]
        if sample_weightmap is not None:
            sample_weightmap[:, :] = sample_weightmap[:, ::-1]
    if 1 in axes and np.random.uniform() < 0.5:
        sample_data[:, :, :] = sample_data[:, :, ::-1]
        if sample_seg is not None:
            sample_seg[:, :, :] = sample_seg[:, :, ::-1]
        if sample_weightmap is not None:
            sample_weightmap[:, :, :] = sample_weightmap[:, :, ::-1]
    if 2 in axes and len(sample_data.shape) == 4:
        if np.random.uniform() < 0.5:
            sample_data[:, :, :, :] = sample_data[:, :, :, ::-1]
            if sample_seg is not None:
                sample_seg[:, :, :, :] = sample_seg[:, :, :, ::-1]
            if sample_weightmap is not None:
                sample_weightmap[:, :, :, :] = sample_weightmap[:, :, :, ::-1]
    return sample_data, sample_seg, sample_weightmap
