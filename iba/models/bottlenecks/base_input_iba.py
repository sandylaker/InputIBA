from .base_iba import BaseIBA
import torch


class BaseInputIBA(BaseIBA):
    def __init__(self,
                 input_tensor,
                 input_mask,
                 sigma=1.0,
                 initial_alpha=5.0,
                 input_mean=None,
                 input_std=None,
                 progbar=False,
                 reverse_lambda=False,
                 combine_loss=False,
                 device='cuda:0'):
        super(BaseInputIBA, self).__init__(sigma=sigma,
                                           initial_alpha=initial_alpha,
                                           input_mean=input_mean,
                                           input_std=input_std,
                                           progbar=progbar,
                                           reverse_lambda=reverse_lambda,
                                           combine_loss=combine_loss,
                                           device=device)
        self.input_tensor = input_tensor
        self.input_mask = input_mask

    @staticmethod
    def kl_div(x,
               image_mask,
               lambda_,
               mean_x,
               std_x):
        """
        x: unmasked variable
        img_mask: mask generated from GAN
        lambda_: learning parameter, img mask
        mean_x: mean of the noise applied to x
        std_x: std of the noise applied to x
        """
        r_norm = (x - mean_x + image_mask *
                  (mean_x - x)) / ((1 - image_mask * lambda_) * std_x)
        var_z = (1 - lambda_) ** 2 / (1 - image_mask * lambda_) ** 2

        log_var_z = torch.log(var_z)

        mu_z = r_norm * lambda_

        capacity = -0.5 * (1 + log_var_z - mu_z ** 2 - var_z)
        return capacity