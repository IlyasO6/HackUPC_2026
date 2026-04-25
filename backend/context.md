# Context Document: HackUPC 2026 - Mecalux Warehouse Optimizer

## 1. Challenge Overview
* **Objective**: The primary goal is to place storage bays in a warehouse in the cheapest way possible while utilizing the largest amount of area.
* **Terminology**: 
    * A Frame + Beam = Bay.
    * Many Bays = Row.

## 2. Input Specifications
The evaluation algorithm will receive 4 distinct CSV files for a given case.

### WAREHOUSE.CSV
* **Purpose**: Defines the shape and size of the warehouse.
* **Format**: `Coord X, Coord Y`.
* **Constraint**: The walls of the warehouse will always be axis-aligned.

### OBSTACLES.CSV
* **Purpose**: Contains the locations and dimensions of unusable spaces (obstacles) within the warehouse.
* **Format**: `Coord X, Coord Y, Width, Depth`.
* **Constraint**: Obstacles will always be rectangular boxes.

### CEILING.CSV
* **Purpose**: Defines the maximum allowed height at different X-coordinates.
* **Format**: `Coord X, Ceiling Height`.

### TYPES_OF_BAYS.CSV
* **Purpose**: Defines the inventory of bay types available for placement.
* **Format**: `Id, Width, Depth, Height, Gap, nLoads, Price`.

## 3. Expected Output
* **Format**: The final generated solution must output the placement details in the following structure: `Id, X, Y, Rotation`.

## 4. Evaluation Criteria
* **Quality Metric (Q)**: The algorithmic efficiency is evaluated using a specific maximization formula: `Q = (sum(bay area) / area warehouse) - (price / loads)`.
* **Presentation Requirements**: The final score also heavily weights the presentation layer, including the visual rendering of the solution and any implemented UI features.

## 5. Judging Rules and Edge Cases
* **Execution Time**: When judging, the algorithm will run locally and must finish executing in under 30 seconds.
* **Test Case Scale**: Judging tests will not include "crazy edge cases," but the test datasets may be significantly larger than the provided sample examples.
* **Boundary Rules**: Bays are permitted to share boundaries with one another as well as with the warehouse walls. For example, if a bay positioned at (0,0) has a width of 1000, the next adjacent bay can be placed exactly at (1000,0).