import torch
import numpy as np

def get_sr_flag(epoch, sr):
    # return epoch >= 5 and sr
    return sr

class BNOptimizer():

    @staticmethod
    def updateBN(sr_flag, module_list, s, prune_idx, epoch, idx2mask=None, opt=None):
        if sr_flag:
            # s = s if epoch <= opt.epochs * 0.5 else s * 0.01
            for idx in prune_idx:
                # Squential(Conv, BN, Lrelu)
                conv_layer = module_list[idx][0]
                conv_layer_weight = conv_layer.weight.data.cpu().numpy()
                abs_sum = np.sum(np.abs(conv_layer_weight.reshape(conv_layer_weight.shape[0],-1)),axis=-1)
                small, large = min(abs_sum), max(abs_sum)
                abs_sum = (abs_sum - small) / (large-small)
                abs_sum = abs_sum + 0.25
                reweight = torch.from_numpy(abs_sum).cuda()
                # bn_module = module_list[idx][1]
                bn_module = module_list[idx][1] if type(
                    module_list[idx][1]).__name__ == 'BatchNorm2d' else module_list[idx][0]
                #bn_module.weight.grad.data.add_(s * torch.sign(bn_module.weight.data))  # L1
                bn_module.weight.grad.data.add_(s * (1/reweight) * torch.sign(bn_module.weight.data))  # L1
            if idx2mask:
                for idx in idx2mask:
                    # bn_module = module_list[idx][1]
                    bn_module = module_list[idx][1] if type(
                        module_list[idx][1]).__name__ == 'BatchNorm2d' else module_list[idx][0]
                    #bn_module.weight.grad.data.add_(0.5 * s * torch.sign(bn_module.weight.data) * (1 - idx2mask[idx].cuda()))
                    bn_module.weight.grad.data.sub_(0.99 * s * torch.sign(bn_module.weight.data) * idx2mask[idx].cuda())

def parse_module_defs(module_defs):

    CBL_idx = []
    Conv_idx = []
    ignore_idx = set()
    for i, module_def in enumerate(module_defs):
        if module_def['type'] == 'convolutional':
            if module_def['batch_normalize'] == '1':
                CBL_idx.append(i)
            else:
                Conv_idx.append(i)
            if module_defs[i+1]['type'] == 'maxpool' and module_defs[i+2]['type'] == 'route':
                #spp?????????CBL?????? ??????tiny
                ignore_idx.add(i)
            if module_defs[i+1]['type'] == 'route' and 'groups' in module_defs[i+1]:
                ignore_idx.add(i)
            if module_defs[i+1]['type'] == 'convolutional_nobias':
                ignore_idx.add(i)
            if module_defs[i + 1]['type'] == 'maxpool' and module_defs[i + 2]['type'] == 'maxpool':
                # sppf?????????CBL??????
                ignore_idx.add(i)
        elif module_def['type'] == 'convolutional_noconv':
            CBL_idx.append(i)
            ignore_idx.add(i)
        elif module_def['type'] == 'shortcut':
            ignore_idx.add(i-1)
            identity_idx = (i + int(module_def['from']))
            if module_defs[identity_idx]['type'] == 'convolutional':
                ignore_idx.add(identity_idx)
            elif module_defs[identity_idx]['type'] == 'shortcut':
                ignore_idx.add(identity_idx - 1)

        elif module_def['type'] == 'upsample':
            #????????????????????????????????????
            ignore_idx.add(i - 1)


    prune_idx = [idx for idx in CBL_idx if idx not in ignore_idx]

    return CBL_idx, Conv_idx, prune_idx


def parse_module_defs2(module_defs):
    CBL_idx = []
    Conv_idx = []
    shortcut_idx = dict()
    shortcut_all = set()
    ignore_idx = set()
    for i, module_def in enumerate(module_defs):
        if module_def['type'] == 'convolutional':
            if module_def['batch_normalize'] == '1':
                CBL_idx.append(i)
            else:
                Conv_idx.append(i)
            if module_defs[i + 1]['type'] == 'maxpool' and module_defs[i + 2]['type'] == 'route':
                # spp?????????CBL?????? ??????spp???tiny
                ignore_idx.add(i)
            if module_defs[i + 1]['type'] == 'route' and 'groups' in module_defs[i + 1]:
                ignore_idx.add(i)
            if module_defs[i + 1]['type'] == 'maxpool' and module_defs[i + 2]['type'] == 'maxpool':
                # sppf?????????CBL??????
                ignore_idx.add(i)

        elif module_def['type'] == 'convolutional_noconv':
            CBL_idx.append(i)

        elif module_def['type'] == 'upsample':
            # ????????????????????????????????????
            ignore_idx.add(i - 1)

        elif module_def['type'] == 'shortcut':
            identity_idx = (i + int(module_def['from']))
            if module_defs[identity_idx]['type'] == 'convolutional':

                # ignore_idx.add(identity_idx)
                shortcut_idx[i - 1] = identity_idx
                shortcut_all.add(identity_idx)
            elif module_defs[identity_idx]['type'] == 'shortcut':

                # ignore_idx.add(identity_idx - 1)
                shortcut_idx[i - 1] = identity_idx - 1
                shortcut_all.add(identity_idx - 1)
            shortcut_all.add(i - 1)

    prune_idx = [idx for idx in CBL_idx if idx not in ignore_idx]

    return CBL_idx, Conv_idx, prune_idx, shortcut_idx, shortcut_all


def gather_bn_weights(module_list, prune_idx):

    size_list = [module_list[idx][1].weight.data.shape[0] if type(module_list[idx][1]).__name__ == 'BatchNorm2d' else module_list[idx][0].weight.data.shape[0] for idx in prune_idx]

    bn_weights = torch.zeros(sum(size_list))
    index = 0
    for idx, size in zip(prune_idx, size_list):
        bn_weights[index:(index + size)] = module_list[idx][1].weight.data.abs().clone() if type(module_list[idx][1]).__name__ == 'BatchNorm2d' else module_list[idx][0].weight.data.abs().clone()
        index += size

    return bn_weights
