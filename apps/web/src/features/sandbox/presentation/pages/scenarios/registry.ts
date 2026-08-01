export interface SandboxDemo {
  id: string;
  name: string;
  description: string;
  route: string;
}

export const sandboxDemos: SandboxDemo[] = [
  {
    id: "rchannel-denoise",
    name: "ImageNet-100 R-Channel Denoising",
    description: "Salt & pepper noise denoising demo on 100 ImageNet classes",
    route: "/sandbox/rchannel-denoise",
  },
  {
    id: "classify",
    name: "Classify Sandbox",
    description: "Sandbox environment for the classify workflow",
    route: "/sandbox/classify",
  },
];
