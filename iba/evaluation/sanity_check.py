from iba.models.net import Attributor
import torch
import numpy as np
from skimage.metrics import structural_similarity
from copy import deepcopy
from iba.models import get_module
from .base import BaseEvaluation
from mmcv import get_logger
import os.path as osp
import mmcv


def weights_init(m):
    if isinstance(m, torch.nn.Conv2d):
        torch.nn.init.xavier_uniform_(m.weight)
        torch.nn.init.zeros_(m.bias)
    elif isinstance(m, torch.nn.Linear):
        torch.nn.init.normal_(m.weight, mean=0, std=0.05)
        torch.nn.init.zeros_(m.bias)


def perturb_model(model, layers):
    for layer in layers:
        module = get_module(model, layer)
        module.apply(weights_init)


class SanityCheck(BaseEvaluation):

    def __init__(self, attributor: Attributor):
        self.attributor = attributor
        self.ori_state_dict = deepcopy(self.attributor.classifier.state_dict())
        self.model_layers = self.filter_names(
            [n[0] for n in self.attributor.classifier.named_modules()])
        self.logger = get_logger('iba')

    def reload(self):
        self.logger.info('Reload state dict')
        self.attributor.classifier.load_state_dict(self.ori_state_dict)
        self.attributor.classifier.to(self.attributor.device)
        self.attributor.classifier.eval()
        for p in self.attributor.classifier.parameters():
            p.requires_grad = False

    def evaluate(  # noqa
            self,
            heatmap,
            img,
            target,
            attribution_cfg,
            perturb_layers,
            check='gan',
            save_dir=None,
            save_heatmaps=False):
        """Apply sanity check to the attribution method with a single image. Given a list `perturb_layers = ['a', 'b',
         'c']`. There will be `len(perturb_layers)` perturbation settings. First, 'a' and all the subsequent layers
         will be perturbed. Next, 'b' and all the subsequent layers will be perturbed. Then, the similar for 'c'.
         For each perturbation setting, a SSIM value will be computed. In the end, a dict containing all the SSIM
         values will be returned.

        Args:
            heatmap (np.ndarray): heatmap generated by the unperturbed model. It has `dtype` of `np.uint8` and
                shape of (h, w).
            img (torch.Tensor): input image with shape (3, h, w).
            target (int): class label of the image.
            attribution_cfg (dict): attribution configurations.
            perturb_layers (list): layers denoting the perturbed range of the model.
            check (str, optional): which component to check, can be either 'gan' or 'img_iba'.
            save_dir (str, optional): directory for saving the results. Only useful when `save_heatmaps` is True.
            save_heatmaps (bool, optional): if True, save the heatmaps produced by the perturbed models along with
                the original heatmap.

        Returns:
            ssim_all (dict): key 'ssim_val'. ssim values under all the perturbation settings.
        """
        assert check in [
            'gan', 'img_iba'
        ], f"check must be one of 'gan' or 'img_iba', but got {check}"
        if save_heatmaps:
            assert save_dir is not None, "if save_masks, save_dir must not be None"
            if save_dir is not None:
                mmcv.mkdir_or_exist(save_dir)
        attr_cfg = deepcopy(attribution_cfg)
        model_layers = deepcopy(self.model_layers)
        # start from the last layer
        model_layers = model_layers[::-1]
        ssim_all = []
        for l in perturb_layers:
            # reload state_dict
            self.reload()
            self.logger.info(f'Perturb {l} and subsequent layers')
            p_layers = []
            for m in model_layers:
                if l != m:
                    p_layers.append(m)
                else:
                    break
            p_layers.append(l)
            self.logger.info(
                f"Following layers will be perturbed: [{', '.join(p_layers)}]")
            ssim_val = self.sanity_check_single(img=img,
                                                target=target,
                                                attr_cfg=attr_cfg,
                                                perturb_layers=p_layers,
                                                ori_img_mask=heatmap,
                                                check=check,
                                                save_dir=save_dir,
                                                save_heatmaps=save_heatmaps)
            self.logger.info(f'ssim_val: {ssim_val}')
            ssim_all.append(ssim_val)
        if save_heatmaps:
            self.attributor.show_mask(heatmap,
                                      out_file=osp.join(save_dir,
                                                        'ori_img_mask'))
        return dict(ssim_all=ssim_all)

    def sanity_check_single(self,
                            img,
                            target,
                            attr_cfg,
                            perturb_layers,
                            ori_img_mask,
                            check='img_iba',
                            save_dir=None,
                            save_heatmaps=False):
        closure = self.attributor.get_closure(self.attributor.classifier,
                                              target,
                                              self.attributor.use_softmax)

        _ = self.attributor.train_iba(img, closure, attr_cfg['iba'])
        if check == 'gan':
            perturb_model(self.attributor.classifier, perturb_layers)
            gen_img_mask = self.attributor.train_gan(img, attr_cfg['gan'])
        else:
            gen_img_mask = self.attributor.train_gan(img, attr_cfg['gan'])
            perturb_model(self.attributor.classifier, perturb_layers)
        img_mask, _ = self.attributor.train_img_iba(
            self.attributor.cfg['img_iba'],
            img,
            gen_img_mask=gen_img_mask,
            closure=closure,
            attr_cfg=attr_cfg['img_iba'])
        ssim_val = self.ssim(ori_img_mask, img_mask)
        if save_heatmaps:
            img_mask = (img_mask * 255).astype(np.uint8)
            self.attributor.show_mask(
                img_mask,
                out_file=osp.join(save_dir,
                                  f"{perturb_layers[-1]}_{ssim_val:.3f}"))
        return ssim_val

    @staticmethod
    def ssim(mask_1, mask_2):
        mask_1 = SanityCheck.convert_mask(mask_1)
        mask_2 = SanityCheck.convert_mask(mask_2)
        return structural_similarity(mask_1, mask_2, win_size=5, data_range=255)

    @staticmethod
    def convert_mask(m):
        if m.dtype in (np.float64, np.float32, np.float16, np.float128):
            assert m.max() <= 1.0
            m = (m * 255).astype(np.uint8)
        return m

    @staticmethod
    def filter_names(names):
        res = []
        for i in range(len(names) - 1):
            if not names[i] in names[i + 1]:
                res.append(names[i])
        res.append(names[-1])
        return res
