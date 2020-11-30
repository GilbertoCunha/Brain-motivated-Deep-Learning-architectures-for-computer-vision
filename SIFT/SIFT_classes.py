from kornia.feature.siftdesc import SIFTDescriptor
from RetinaVVS.RetinaVVS_class import RetinaVVS
import torch.nn.functional as F
import torch.nn as nn
import torch


class SIFT(nn.Module):
    """
    A SIFT class that automatically processes one batch of images using kornia's sift descriptor
    """
    def __init__(self, patch_size=65, num_ang_bins=8, num_spatial_bins=4, clip_val=0.2, root_sift=False):
        super(SIFT, self).__init__()
        self.ps = patch_size
        self.sift = SIFTDescriptor(patch_size, num_ang_bins, num_spatial_bins, root_sift, clip_val)

    def forward(self, image_batch):
        c = image_batch.shape[1]  # Number of image channels
        ps = self.ps  # Patch size

        # Get SIFT outputs
        patches = image_batch.unfold(2, ps, ps).unfold(3, ps, ps).reshape(-1, c, ps, ps)
        p_c = torch.split(patches, 1, dim=1)
        outputs = torch.stack([self.sift(image) for image in p_c]).permute(1, 0, 2)

        return outputs


class SIFTRetinaStart(RetinaVVS):
    def __init__(self, hparams):
        super(SIFTRetinaStart, self).__init__(hparams)

        # Gather hparams
        input_shape = hparams["input_shape"]
        patch_size = hparams["patch_size"]
        self.patch_size = patch_size

        # Model identifiers
        self.name += f"_PatchSize{patch_size}"

        # Modify model parameters
        # features = 32 * input_shape[1] * input_shape[2] + 128 * input_shape[0] * int(input_shape[1] / patch_size) ** 2
        vvs_features = 32 * input_shape[1] * input_shape[2]
        features = 128 * input_shape[0] * int(input_shape[1] / patch_size) ** 2
        self.sift_fc = nn.Linear(in_features=features, out_features=features)
        self.vvs_fc = nn.Linear(in_features=vvs_features+features, out_features=1024)
        self.sift = SIFT(patch_size=patch_size)

    def forward(self, tensor):
        batch_size = tensor.shape[0]

        # Retina forward pass
        t = self.pad(self.ret_bn1(F.relu(self.inputs(tensor))))
        t = self.pad(self.ret_bn2(F.relu(self.ret_conv(t))))
        
        # Apply sift after retina
        sift_t = self.sift(tensor).reshape(batch_size, -1)
        sift_t = self.dropout(F.relu(self.sift_fc(sift_t)))

        # VVS forward pass
        for conv, bn in zip(self.vvs_conv, self.vvs_bn):
            t = self.pad(bn(F.relu(conv(t))))
        # t = torch.cat((t.reshape(batch_size, -1), self.sift(tensor).reshape(batch_size, -1)), dim=-1)
        t = torch.cat((t.reshape(batch_size, -1), sift_t.reshape(batch_size, -1)), dim=-1)
        # t = t.reshape(batch_size, -1) + sift_t.reshape(batch_size, -1)
        t = self.dropout(F.relu(self.vvs_fc(t)))
        t = self.outputs(t)

        return t


class SIFTVVSEnd(RetinaVVS):
    def __init__(self, hparams):
        super(SIFTVVSEnd, self).__init__(hparams)

        # Gather hparams
        input_shape = hparams["input_shape"]
        patch_size = hparams["patch_size"]
        self.patch_size = patch_size

        # Model Parameters
        self.name += f"_PatchSize{patch_size}"

        # Change model parameters
        in_features = 32 * input_shape[0] * int(input_shape[1] / patch_size) ** 2 * 128
        self.vvs_fc = nn.Linear(in_features=in_features, out_features=1024)
        self.sift = SIFT(patch_size=patch_size)

    def forward(self, tensor):
        batch_size = tensor.shape[0]

        # Retina forward pass
        t = self.pad(self.ret_bn1(F.relu(self.inputs(tensor))))
        t = self.pad(self.ret_bn2(F.relu(self.ret_conv(t))))

        # VVS forward pass
        for conv, bn in zip(self.vvs_conv, self.vvs_bn):
            t = self.pad(bn(F.relu(conv(t))))
        t = self.sift(t).reshape(batch_size, -1)
        t = self.dropout(F.relu(self.vvs_fc(t)))
        t = self.outputs(t)

        return t


class SIFTBoth(RetinaVVS):
    def __init__(self, hparams):
        super(SIFTBoth, self).__init__(hparams)

        # Gather hparams
        input_shape = hparams["input_shape"]
        patch_size = hparams["patch_size"]
        self.patch_size = patch_size

        # Model Parameters
        self.name += f"_PatchSize{patch_size}"

        # Modify model parameters
        in_features = 33 * input_shape[0] * int(input_shape[1] / patch_size) ** 2 * 128
        self.vvs_fc = nn.Linear(in_features=in_features, out_features=1024)
        self.sift = SIFT(patch_size=patch_size)

    def forward(self, tensor):
        batch_size = tensor.shape[0]

        # Retina forward pass
        t = self.pad(self.ret_bn1(F.relu(self.inputs(tensor))))
        t = self.pad(self.ret_bn2(F.relu(self.ret_conv(t))))
        st = self.sift(t)

        # VVS forward pass
        for conv, bn in zip(self.vvs_conv, self.vvs_bn):
            t = self.pad(bn(F.relu(conv(t))))
        t = self.sift(t).reshape(batch_size, -1)
        t = torch.cat((t.reshape(batch_size, -1), st.reshape(batch_size, -1)), dim=-1)
        t = self.dropout(F.relu(self.vvs_fc(t)))
        t = self.outputs(t)

        return t