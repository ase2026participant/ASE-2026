
// C program to find date after adding 
// given number of days. 
// we have changed the single line "if-else" condition to multiline "if-else"
#include <stdio.h>
#include <stdlib.h> 
#include <assert.h>

#define D_MIN   1
#define D_MAX  31
#define M_MIN   1
#define M_MAX  12
#define Y_MIN 1900
#define Y_MAX 2100
#define X_MIN   0
#define X_MAX 1000

const int MAX_VALID_YR = 9999; 
const int MIN_VALID_YR = 1800; 


int final_d_1 = 0;
int final_d_2 = 0;
int final_m_1 = 0;
int final_m_2 = 0;
int final_y_1 = 0;
int final_y_2 = 0;

// Return if year is leap year or not. 
int isLeap_1(int y) 
{ 
    if (y%100 != 0 && y%4 == 0 || y %400 == 0) 
        return 1; 
  
    return 0; 
} 

// Return if year is leap year or not. 
int isLeap_2(int y) 
{ 
    if (y%100 != 0 && y%4 == 0 || y %400 == 0) 
        return 1; 
  
    return 0; 
} 

// Returns true if given 
// year is valid or not. 
int isValidDate_1(int d, int m, int y) 
{ 
	// If year, month and day 
	// are not in given range 
	if (y > MAX_VALID_YR || 
		y < MIN_VALID_YR) 
	return 0; 
	if (m < 1 || m > 12) 
	return 0; 
	if (d < 1 || d > 31) 
	return 0; 

	// Handle February month 
	// with leap year 
	if (m == 2) 
	{ 
		if (isLeap_1(y)) 
		return (d <= 29); 
		else
		return (d <= 28); 
	} 

	// Months of April, June, 
	// Sept and Nov must have 
	// number of days less than 
	// or equal to 30. 
	if (m == 4 || m == 6 || 
		m == 9 || m == 11) 
		return (d <= 30); 

	return 1; 
} 

// Returns true if given 
// year is valid or not. 
int isValidDate_2(int d, int m, int y) 
{ 
	// If year, month and day 
	// are not in given range 
	if (y > MAX_VALID_YR || 
		y < MIN_VALID_YR) 
	return 0; 
	if (m < 1 || m > 12) 
	return 0; 
	if (d < 1 || d > 31) 
	return 0; 

	// Handle February month 
	// with leap year 
	if (m == 2) 
	{ 
		if (isLeap_2(y)) 
		return (d <= 29); 
		else
		return (d <= 28); 
	} 

	// Months of April, June, 
	// Sept and Nov must have 
	// number of days less than 
	// or equal to 30. 
	if (m == 4 || m == 6 || 
		m == 9 || m == 11) 
		return (d <= 30); 

	return 1; 
} 
  
// Given a date, returns number of days elapsed 
// from the  beginning of the current year (1st 
// jan). 
int offsetDays_1(int d, int m, int y) 
{ 
    int offset = d; 
  
    switch (m - 1) 
    { 
    case 11: 
        offset += 30; 
    case 10: 
        offset += 31; 
    case 9: 
        offset += 30; 
    case 8: 
        offset += 31; 
    case 7: 
        offset += 31; 
    case 6: 
        offset += 30; 
    case 5: 
        offset += 31; 
    case 4: 
        offset += 30; 
    case 3: 
        offset += 31; 
    case 2: 
        offset += 28; 
    case 1: 
        offset += 31; 
    } 
  
    if (isLeap_1(y) && m > 2) 
        offset += 1; 
  
    return offset; 
} 

// Given a date, returns number of days elapsed 
// from the  beginning of the current year (1st 
// jan). 
int offsetDays_2(int d, int m, int y) 
{ 
    int offset = d; 
  
    switch (m - 1) 
    { 
    case 11: 
        offset += 30; 
    case 10: 
        offset += 31; 
    case 9: 
        offset += 30; 
    case 8: 
        offset += 31; 
    case 7: 
        offset += 31; 
    case 6: 
        offset += 30; 
    case 5: 
        offset += 31; 
    case 4: 
        offset += 30; 
    case 3: 
        offset += 31; 
    case 2: 
        offset += 28; 
    case 1: 
        offset += 31; 
    } 
  
    if (isLeap_2(y) && m > 2) 
        offset += 1; 
  
    return offset; 
} 
  
// Given a year and days elapsed in it, finds 
// date by storing results in d and m. 
void revoffsetDays_1(int offset, int y, int *d, int *m) 
{ 
    int month[13] = { 0, 31, 28, 31, 30, 31, 30, 
                      31, 31, 30, 31, 30, 31 }; 
  
    if (isLeap_1(y)) 
        month[2] = 29; 
  
    int i; 
    for (i = 1; i <= 12; i++) 
    { 
        if (offset <= month[i]) 
            break; 
        offset = offset - month[i]; 
    } 
  
    *d = offset; 
    *m = i; 
} 

// Given a year and days elapsed in it, finds 
// date by storing results in d and m. 
void revoffsetDays_2(int offset, int y, int *d, int *m) 
{ 
    int month[13] = { 0, 30, 28, 31, 30, 31, 30, 
                      31, 31, 30, 31, 30, 31 }; 
  
    if (isLeap_2(y)) 
        month[2] = 29; 
  
    int i; 
    for (i = 1; i <= 12; i++) 
    { 
        if (offset <= month[i]) 
            break; 
        offset = offset - month[i]; 
    } 
  
    *d = offset; 
    *m = i; 
} 

// Add x days to the given date. 
void addDays_1(int d1, int m1, int y1, int x) 
{ 
    int offset1 = offsetDays_1(d1, m1, y1); 
    int remDays=0;

    if (isLeap_1(y1))
	{
		remDays=366-offset1;
	}
     else
	{
		remDays=365-offset1;
	}
	
  
    // y2 is going to store result year and 
    // offset2 is going to store offset days 
    // in result year. 
    int y2, offset2; 
    if (x <= remDays) 
    { 
        y2 = y1; 
        offset2 = offset1 + x; 
    } 
  
    else
    { 
        // x may store thousands of days. 
        // We find correct year and offset 
        // in the year. 
        x -= remDays; 
        y2 = y1 + 1; 
	int y2days=0;
	if (isLeap_1(y2))
	{
	y2days=366;
	}
	else
	{
	y2days=365;
	}
        while (x >= y2days) 
        { 
		x -= y2days; 
		y2++; 
		if (isLeap_1(y2))
		{
		y2days=366;
		}
		else
		{
		y2days=365;
		}
        } 
        offset2 = x; 
    } 
  
    // Find values of day and month from 
    // offset of result year. 
    int m2, d2; 
    revoffsetDays_1(offset2, y2, &d2, &m2); 
    
    final_d_1 = d2;
    final_m_1 = m2;
    final_y_1 = y2;
    printf("%d- %d- %d", d2, m2, y2);
    //cout << "d2 = " << d2 << ", m2 = " << m2 
         //<< ", y2 = " << y2; 
}

// Add x days to the given date. 
void addDays_2(int d1, int m1, int y1, int x) 
{ 
    int offset1 = offsetDays_2(d1, m1, y1); 
    int remDays=0;

    if (isLeap_2(y1))
	{
		remDays=366-offset1;
	}
     else
	{
		remDays=365-offset1;
	}
	
  
    // y2 is going to store result year and 
    // offset2 is going to store offset days 
    // in result year. 
    int y2, offset2; 
    if (x <= remDays) 
    { 
        y2 = y1; 
        offset2 = offset1 + x; 
    } 
  
    else
    { 
        // x may store thousands of days. 
        // We find correct year and offset 
        // in the year. 
        x -= remDays; 
        y2 = y1 + 1; 
	int y2days=0;
	if (isLeap_2(y2))
	{
	y2days=366;
	}
	else
	{
	y2days=365;
	}
        while (x >= y2days) 
        { 
		x -= y2days; 
		y2++; 
		if (isLeap_2(y2))
		{
		y2days=366;
		}
		else
		{
		y2days=365;
		}
        } 
        offset2 = x; 
    } 
  
    // Find values of day and month from 
    // offset of result year. 
    int m2, d2; 
    revoffsetDays_2(offset2, y2, &d2, &m2); 
    
    final_d_2 = d2;
    final_m_2 = m2;
    final_y_2 = y2;
    printf("%d- %d- %d", d2, m2, y2);
    //cout << "d2 = " << d2 << ", m2 = " << m2 
         //<< ", y2 = " << y2; 
}
  
// Driven Program 
int test_driver() 
{ 
	/* declare symbolic inputs */
    int d = nondet_int();
    int m = nondet_int();
    int y = nondet_int();
    int x = nondet_int();

    /* restrict them to the ranges you want CBMC to explore */
    __CPROVER_assume(d >= D_MIN && d <= D_MAX);
    __CPROVER_assume(m >= M_MIN && m <= M_MAX);
    __CPROVER_assume(y >= Y_MIN && y <= Y_MAX);
    __CPROVER_assume(x >= X_MIN && x <= X_MAX);
//int d = 14, m = 3, y = 2015; 
    //int x = 366; 
    if (isValidDate_1(d, m, y)){
        addDays_1(d, m, y, x);
	}

    if (isValidDate_2(d, m, y)){
        addDays_2(d, m, y, x);
	}

    assert((final_d_1 != final_d_2) || (final_m_1 != final_m_2) || (final_y_1 != final_y_2));
    assert((final_d_1 == final_d_2) && (final_m_1 == final_m_2) && (final_y_1 == final_y_2));
    return 0; 
} 

