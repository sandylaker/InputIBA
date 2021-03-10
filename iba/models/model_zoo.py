from torchvision import models
import torch
from copy import deepcopy


def build_classifiers(cfg):
    cfg = deepcopy(cfg)
    model_name = cfg.pop('type')
    pretrained = cfg.pop('pretrained', True)
    assert isinstance(pretrained, (bool, str))
    # if pretrained is a path, first build a randomly initialized model, then load the pretrained weight
    # if pretrained is a bool, just call the torchvision's builder, and pass the boolean to the builder
    if isinstance(pretrained, str):
        pretrained_ = False
    else:
        pretrained_ = pretrained
    _builder = getattr(models, model_name)
    cfg.update({"pretrained": pretrained_})
    model = _builder(**cfg)
    if pretrained:
        ckpt = torch.load(pretrained)
        model.load_state_dict(ckpt)
    return model


def get_module(model, module):
    r"""Returns a specific layer in a model based.
    Shameless copy from `TorchRay
    <https://github.com/facebookresearch/TorchRay/blob/master/torchray/attribution/common.py>`_

    :attr:`module` is either the name of a module (as given by the
    :func:`named_modules` function for :class:`torch.nn.Module` objects) or
    a :class:`torch.nn.Module` object. If :attr:`module` is a
    :class:`torch.nn.Module` object, then :attr:`module` is returned unchanged.
    If :attr:`module` is a str, the function searches for a module with the
    name :attr:`module` and returns a :class:`torch.nn.Module` if found;
    otherwise, ``None`` is returned.
    Args:
        model (:class:`torch.nn.Module`): model in which to search for layer.
        module (str or :class:`torch.nn.Module`): name of layer (str) or the
            layer itself (:class:`torch.nn.Module`).
    Returns:
        :class:`torch.nn.Module`: specific PyTorch layer (``None`` if the layer
            isn't found).
    """
    if isinstance(module, torch.nn.Module):
        return module

    assert isinstance(module, str)
    if module == '':
        return model

    for name, curr_module in model.named_modules():
        if name == module:
            return curr_module

    return None