Concept Check

Difference between .loc[] and .iloc[]?
.loc[] selects rows labels and columns names as df.loc[1:"Age"] while .iloc[] selects data on base on integer location df.iloc[1:,2]

How do you filter rows where two conditions are both true?
df[(df["Sex"] == "male") & (df["Age"] > 30)]

What does .groupby() return before you call an aggregation on it?
just it stores and separates the values on the basis of group by it returns a Groupby object

How do you check for and count missing values in a DataFrame?
df.isnull().sum()

What’s the difference between df.copy() and just assigning df2 = df?
dp.copy() makes a new copy in the different location of memaory and chnage in one do not change in other df while assignment poits to same 
df and chnage in one df affects to other df.