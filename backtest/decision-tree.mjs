function finite(value) {
  return Number.isFinite(value);
}

function safeDivide(numerator, denominator) {
  if (!finite(numerator) || !finite(denominator) || denominator === 0) return 0;
  return numerator / denominator;
}

function round(value, digits = 4) {
  if (!finite(value)) return 0;
  return Number(value.toFixed(digits));
}

function classCounts(rows) {
  const counts = new Map();
  for (const row of rows) {
    counts.set(row.label, (counts.get(row.label) || 0) + 1);
  }
  return counts;
}

function distribution(rows) {
  return Array.from(classCounts(rows).entries())
    .map(([label, count]) => ({
      label,
      count,
      sharePct: safeDivide(count, rows.length) * 100
    }))
    .sort((left, right) => right.count - left.count);
}

function majority(rows) {
  return distribution(rows)[0] || { label: "", count: 0, sharePct: 0 };
}

function gini(rows) {
  if (!rows.length) return 0;
  const counts = classCounts(rows);
  let sum = 0;
  for (const count of counts.values()) {
    const probability = count / rows.length;
    sum += probability ** 2;
  }
  return 1 - sum;
}

function uniqueSorted(values) {
  return Array.from(new Set(values.filter(finite))).sort((left, right) => left - right);
}

function candidateThresholds(rows, featureKey, maxThresholds) {
  const values = uniqueSorted(rows.map((row) => row.values[featureKey]));
  if (values.length <= 1) return [];

  if (values.length <= maxThresholds + 1) {
    return values.slice(1).map((value, index) => (values[index] + value) / 2);
  }

  return Array.from({ length: maxThresholds }, (_, index) => {
    const pct = (index + 1) / (maxThresholds + 1);
    const valueIndex = Math.max(1, Math.min(values.length - 1, Math.floor(pct * values.length)));
    return (values[valueIndex - 1] + values[valueIndex]) / 2;
  });
}

function splitRows(rows, featureKey, threshold) {
  const left = [];
  const right = [];

  for (const row of rows) {
    if (row.values[featureKey] <= threshold) {
      left.push(row);
    } else {
      right.push(row);
    }
  }

  return { left, right };
}

function bestSplit(rows, features, options) {
  const parentGini = gini(rows);
  let best = null;

  for (const feature of features) {
    for (const threshold of candidateThresholds(rows, feature.key, options.maxThresholds)) {
      const { left, right } = splitRows(rows, feature.key, threshold);
      if (left.length < options.minSamplesLeaf || right.length < options.minSamplesLeaf) continue;

      const weightedGini = ((left.length / rows.length) * gini(left)) + ((right.length / rows.length) * gini(right));
      const gain = parentGini - weightedGini;

      if (!best || gain > best.gain) {
        best = {
          feature,
          threshold,
          gain,
          left,
          right,
          parentGini,
          weightedGini
        };
      }
    }
  }

  return best;
}

function makeLeaf(rows, depth, classNames) {
  const top = majority(rows);
  return {
    type: "leaf",
    depth,
    samples: rows.length,
    prediction: top.label,
    predictionName: classNames[top.label] || String(top.label),
    purityPct: round(top.sharePct, 2),
    distribution: distribution(rows).map((item) => ({
      ...item,
      name: classNames[item.label] || String(item.label),
      sharePct: round(item.sharePct, 2)
    }))
  };
}

function buildNode(rows, features, options, classNames, depth = 0) {
  const leaf = makeLeaf(rows, depth, classNames);

  if (
    depth >= options.maxDepth ||
    rows.length < options.minSamplesSplit ||
    leaf.purityPct >= options.maxPurityPct
  ) {
    return leaf;
  }

  const split = bestSplit(rows, features, options);
  if (!split || split.gain < options.minGain) return leaf;

  return {
    type: "split",
    depth,
    samples: rows.length,
    prediction: leaf.prediction,
    predictionName: leaf.predictionName,
    purityPct: leaf.purityPct,
    distribution: leaf.distribution,
    featureKey: split.feature.key,
    featureLabel: split.feature.label,
    threshold: split.threshold,
    gain: split.gain,
    left: buildNode(split.left, features, options, classNames, depth + 1),
    right: buildNode(split.right, features, options, classNames, depth + 1)
  };
}

function collectRules(node, rules, path = []) {
  if (node.type === "leaf") {
    rules.push({
      path,
      prediction: node.prediction,
      predictionName: node.predictionName,
      samples: node.samples,
      purityPct: node.purityPct,
      distribution: node.distribution
    });
    return;
  }

  collectRules(node.left, rules, [
    ...path,
    {
      featureKey: node.featureKey,
      featureLabel: node.featureLabel,
      operator: "<=",
      threshold: node.threshold
    }
  ]);
  collectRules(node.right, rules, [
    ...path,
    {
      featureKey: node.featureKey,
      featureLabel: node.featureLabel,
      operator: ">",
      threshold: node.threshold
    }
  ]);
}

function collectImportance(node, importance = new Map()) {
  if (node.type === "leaf") return importance;

  const item = importance.get(node.featureKey) || {
    key: node.featureKey,
    label: node.featureLabel,
    score: 0
  };
  item.score += node.gain * node.samples;
  importance.set(node.featureKey, item);
  collectImportance(node.left, importance);
  collectImportance(node.right, importance);
  return importance;
}

function formatCondition(condition) {
  return `${condition.featureLabel} ${condition.operator} ${round(condition.threshold)}`;
}

export function trainDecisionTree(samples, features, options = {}) {
  const normalizedOptions = {
    maxDepth: options.maxDepth ?? 4,
    minSamplesSplit: options.minSamplesSplit ?? 80,
    minSamplesLeaf: options.minSamplesLeaf ?? 30,
    minGain: options.minGain ?? 0.006,
    maxThresholds: options.maxThresholds ?? 12,
    maxPurityPct: options.maxPurityPct ?? 96,
    classNames: options.classNames || {}
  };
  const rows = samples.filter((row) => row.label !== null && row.label !== undefined);
  const tree = buildNode(rows, features, normalizedOptions, normalizedOptions.classNames);
  const rules = [];
  collectRules(tree, rules);
  const importance = Array.from(collectImportance(tree).values())
    .sort((left, right) => right.score - left.score)
    .map((item) => ({
      ...item,
      score: round(item.score, 4)
    }));

  return {
    options: normalizedOptions,
    samples: rows.length,
    tree,
    rules: rules
      .sort((left, right) => right.samples - left.samples)
      .map((rule, index) => ({
        id: index + 1,
        ...rule,
        conditionText: rule.path.length ? rule.path.map(formatCondition).join(" AND ") : "ALL",
        distributionText: rule.distribution.slice(0, 4).map((item) => `${item.name}:${round(item.sharePct, 1)}%`).join(" | ")
      })),
    importance
  };
}

export function decisionTreeRuleRows(treeResult) {
  return treeResult.rules.map((rule) => ({
    ruleId: rule.id,
    prediction: rule.predictionName,
    samples: rule.samples,
    purityPct: rule.purityPct,
    conditions: rule.conditionText,
    distribution: rule.distributionText
  }));
}

export function decisionTreeImportanceRows(treeResult) {
  return treeResult.importance.map((item, index) => ({
    rank: index + 1,
    feature: item.label,
    featureKey: item.key,
    importance: item.score
  }));
}

export function predictDecisionTree(treeResult, values) {
  const path = [];
  let node = treeResult.tree;

  while (node?.type === "split") {
    const value = values[node.featureKey];
    const useLeft = finite(value) && value <= node.threshold;
    path.push({
      featureKey: node.featureKey,
      featureLabel: node.featureLabel,
      operator: useLeft ? "<=" : ">",
      threshold: node.threshold,
      value
    });
    node = useLeft ? node.left : node.right;
  }

  return {
    prediction: node?.prediction ?? "",
    predictionName: node?.predictionName ?? "",
    samples: node?.samples ?? 0,
    purityPct: node?.purityPct ?? 0,
    distribution: node?.distribution || [],
    path,
    conditionText: path.length ? path.map(formatCondition).join(" AND ") : "ALL"
  };
}
