Concept Check

What is broadcasting in NumPy?
Broadcasting means adding np arrays which may have different shapes and size it extends the small array to extended size as required.

How do you select all rows where a column value > 10 in a 2D array?
array[array[:,1]>10]

Difference between .reshape() and .flatten()?
.reshape() chnages the shape of np array according to parameters as we give to its function and .flatten() flats the 2-d array to a single dimension.

What does axis=0 vs axis=1 mean in np.sum()?
in np.sum() axis=0 menas add elements in a column way and axis=1 add elements in a row way.


How do you generate a random array of shape (5,5)?
import numpy as np
array  = np.random.rand(5, 5)


ndim--->number of dimensions
shape--->tuple deega hamme and single m (3,)-->means ak he dimension m 3 elements
size--->total number of elements
dtype--->data type(int 64 for int for string u4)
zeros--->zeros(5)-->[0.,0.,0.,0.,0.] zeros(2,3) zeros(2,2,2)
same as for ones
full-->full every position with same value full((2,3),5)-->2 row,3 col,5 value
np.eye(3)..>creates a identity matrix of 3x3
arrange(5)=0 1 2 3 4
arrange(2,10)=2-9
arrnge(2,20,2)-->last two means with the gap of two
linspace(2,3,5)--=menas 5 values between 2-3


