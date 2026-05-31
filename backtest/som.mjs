function createRng(seed) {
  let value = seed >>> 0;
  return () => {
    value = (value * 1664525 + 1013904223) >>> 0;
    return value / 2 ** 32;
  };
}

function squaredDistance(left, right) {
  let sum = 0;
  for (let index = 0; index < left.length; index += 1) {
    const diff = left[index] - right[index];
    sum += diff * diff;
  }
  return sum;
}

function gridDistance(left, right) {
  return Math.sqrt(((left.row - right.row) ** 2) + ((left.col - right.col) ** 2));
}

function bmu(weights, vector) {
  let bestIndex = 0;
  let bestDistance = Infinity;
  let secondDistance = Infinity;

  weights.forEach((node, index) => {
    const distance = squaredDistance(node.weight, vector);
    if (distance < bestDistance) {
      secondDistance = bestDistance;
      bestDistance = distance;
      bestIndex = index;
    } else if (distance < secondDistance) {
      secondDistance = distance;
    }
  });

  return {
    index: bestIndex,
    distance: Math.sqrt(bestDistance),
    secondDistance: Math.sqrt(secondDistance)
  };
}

function shuffle(values, rng) {
  const copy = [...values];
  for (let index = copy.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(rng() * (index + 1));
    [copy[index], copy[swapIndex]] = [copy[swapIndex], copy[index]];
  }
  return copy;
}

export function trainSom(vectors, options) {
  const rng = createRng(options.seed);
  const nodeCount = options.rows * options.cols;
  const dimensions = vectors[0]?.length || 0;
  const weights = Array.from({ length: nodeCount }, (_, index) => {
    const source = vectors[Math.floor(rng() * vectors.length)] || Array(dimensions).fill(0);
    return {
      id: index,
      row: Math.floor(index / options.cols),
      col: index % options.cols,
      weight: source.map((value) => value + ((rng() - 0.5) * 0.08))
    };
  });

  const initialRadius = Math.max(options.rows, options.cols) / 2;
  const epochs = Math.max(1, options.epochs);

  for (let epoch = 0; epoch < epochs; epoch += 1) {
    const progress = epoch / epochs;
    const learningRate = options.learningRate * Math.exp(-progress * 3.2);
    const radius = Math.max(0.35, initialRadius * Math.exp(-progress * 3.2));
    const radiusSq = radius ** 2;

    for (const vector of shuffle(vectors, rng)) {
      const winner = bmu(weights, vector);
      const winnerNode = weights[winner.index];

      for (const node of weights) {
        const distance = gridDistance(node, winnerNode);
        if (distance > radius) continue;
        const influence = Math.exp(-(distance ** 2) / (2 * radiusSq));

        for (let dimension = 0; dimension < dimensions; dimension += 1) {
          node.weight[dimension] += influence * learningRate * (vector[dimension] - node.weight[dimension]);
        }
      }
    }
  }

  const quantizationError = vectors.length
    ? vectors.reduce((sum, vector) => sum + bmu(weights, vector).distance, 0) / vectors.length
    : 0;

  return {
    rows: options.rows,
    cols: options.cols,
    dimensions,
    weights,
    quantizationError
  };
}

export function assignSom(model, vector) {
  return bmu(model.weights, vector);
}
