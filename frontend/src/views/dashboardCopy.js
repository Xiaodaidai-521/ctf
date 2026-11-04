export function dashboardCopy(value) {
  return String(value ?? '')
    .replace(/^[🎯🌐📝💡📚📕]\s*/u, '')
    .replace(/^DKT估计掌握率([^，]+)，AKT关注到相关知识与遗忘间隔，S3Rec\/GNN依赖分([^。]+)。/, '掌握度参考值$1，结合相关知识与复习间隔，前置知识参考值$2。')
}
